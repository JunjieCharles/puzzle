"""Private font/room experiments. No real glyph-to-puzzle data belongs in Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from scipy import ndimage
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT.parent / (ROOT.name + '-private') / 'hanzi-floorplan'
SIDE = 360
GRID = 6
CROSS = ndimage.generate_binary_structure(2, 1)


def private_path(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Private output must be outside the repository')
    return path


def components(mask):
    # Eight-connected ink: diagonal strokes must not fragment into pixel islands.
    labels, count = ndimage.label(mask, np.ones((3, 3), dtype=bool))
    if not count:
        raise ValueError('Empty glyph')
    return labels, count


def cell_ink(labels, count):
    step = labels.shape[0] // GRID
    return np.array([
        [np.count_nonzero(labels[r*step:(r+1)*step, c*step:(c+1)*step] == k)
         for r in range(GRID) for c in range(GRID)]
        for k in range(1, count+1)
    ], dtype=float)


def glyph_placement(char, font_path):
    font = ImageFont.truetype(str(font_path), 600)
    box = font.getbbox(char)
    image = Image.new('L', (box[2]-box[0]+8, box[3]-box[1]+8))
    ImageDraw.Draw(image).text((4-box[0], 4-box[1]), char, font=font, fill=255)
    image = image.crop(image.getbbox())
    source_labels, count = components(np.asarray(image) >= 96)
    if count > 36:
        raise ValueError('More ink components than cells')
    # Preserve source component IDs while searching placement; do not merge thin gaps.
    source = Image.fromarray(source_labels.astype('int32'), mode='I')
    best = None
    for scale in (.88, .92, .96):
        factor = SIDE * scale / max(image.size)
        size = tuple(round(v*factor) for v in image.size)
        stamp = source.resize(size, Image.Resampling.NEAREST)
        for dx in (-6, 0, 6):
            for dy in (-6, 0, 6):
                canvas = Image.new('I', (SIDE, SIDE))
                canvas.paste(stamp, ((SIDE-size[0])//2+dx, (SIDE-size[1])//2+dy))
                labels = np.asarray(canvas)
                ink = cell_ink(labels, count)
                totals = ink.sum(axis=1)
                if np.any(totals == 0):
                    continue
                normalized = ink / totals[:, None]
                rows, roots = linear_sum_assignment(-normalized)
                lost = count - normalized.max(axis=0).sum()
                seed_loss = np.sum(normalized[rows, roots] == 0)
                score = (seed_loss, lost, abs(scale-.92)+abs(dx)/1000+abs(dy)/1000)
                if best is None or score < best[0]:
                    best = (score, labels.copy(), ink, roots, (scale, dx, dy))
    if best is None:
        raise ValueError('Glyph vanished during rasterization')
    return best[1:]


def allocate(ink, roots=None, time_limit=10):
    """Connected, disjoint rooms via mixed-integer single-commodity flows.

    Roots and placement are fixed before this solve, so this is not a global
    optimum over all possible font placements and room roots.
    """
    k, n = ink.shape
    if n != 36 or not 1 <= k <= n or np.any(ink.sum(axis=1) == 0):
        raise ValueError('Expected 1..36 nonempty components on a 6x6 grid')
    weights = ink / ink.sum(axis=1)[:, None]
    if roots is None:
        _, roots = linear_sum_assignment(-weights)
    edges = [(a, b) for a in range(n) for b in range(n)
             if abs(a//6-b//6)+abs(a%6-b%6) == 1]
    ne = len(edges)
    nx = k*n
    nv = nx+k*ne
    objective = np.zeros(nv)
    objective[:nx] = (-weights + .008).ravel()
    lower = np.zeros(nv)
    upper = np.r_[np.ones(nx), np.full(k*ne, n-1)]
    for j, root in enumerate(roots):
        lower[j*n+root] = 1
    ri, ci, vals, lo, hi = [], [], [], [], []

    def constraint(items, low, high):
        row = len(lo)
        for col, val in items:
            ri.append(row)
            ci.append(col)
            vals.append(val)
        lo.append(low)
        hi.append(high)

    for a in range(n):
        constraint([(j*n+a, 1) for j in range(k)], 0, 1)
    for j in range(k):
        for e, (a, b) in enumerate(edges):
            f = nx+j*ne+e
            constraint([(f, 1), (j*n+a, -(n-1))], -np.inf, 0)
            constraint([(f, 1), (j*n+b, -(n-1))], -np.inf, 0)
        for a in range(n):
            terms = []
            for e, (u, v) in enumerate(edges):
                if v == a:
                    terms.append((nx+j*ne+e, 1))
                if u == a:
                    terms.append((nx+j*ne+e, -1))
            if a == roots[j]:
                terms += [(j*n+b, 1) for b in range(n) if b != a]
            else:
                terms.append((j*n+a, -1))
            constraint(terms, 0, 0)
    matrix = coo_matrix((vals, (ri, ci)), shape=(len(lo), nv)).tocsc()
    result = milp(objective, integrality=np.r_[np.ones(nx), np.zeros(k*ne)],
                  bounds=Bounds(lower, upper),
                  constraints=LinearConstraint(matrix, lo, hi),
                  options={'time_limit': time_limit, 'mip_rel_gap': .005})
    if result.x is None:
        raise RuntimeError('No feasible allocation within the solver time limit')
    chosen = result.x[:nx].reshape(k, n) > .5
    rooms = np.zeros(n, dtype=int)
    for j in range(k):
        rooms[chosen[j]] = j+1
        if ndimage.label(chosen[j].reshape(6, 6), CROSS)[1] != 1:
            raise RuntimeError('Disconnected solver output')
    kept = (ink*chosen).sum(axis=1)
    stats = {'components': k, 'outside_ink_fraction': float(1-kept.sum()/ink.sum()),
             'worst_component_loss': float(np.max(1-kept/ink.sum(axis=1))),
             'empty_cells': int(np.sum(rooms == 0)), 'solver_status': int(result.status),
             'mip_gap': float(result.mip_gap), 'objective': float(result.fun)}
    return rooms.reshape(6, 6), stats


def panel(labels, rooms, overlay):
    image = Image.new('RGB', (SIDE+4, SIDE+4), 'white')
    draw = ImageDraw.Draw(image)
    step = SIDE//6
    for r in range(6):
        for c in range(6):
            if rooms[r, c] == 0:
                draw.rectangle((2+c*step, 2+r*step, 2+(c+1)*step, 2+(r+1)*step), fill='#e2e5e9')
    if overlay:
        ink_image = Image.new('RGB', (SIDE, SIDE), '#a8a8a8')
        image.paste(ink_image, (2, 2), Image.fromarray((labels > 0).astype('uint8')*255))
    draw = ImageDraw.Draw(image)
    for r in range(6):
        for c in range(6):
            if c < 5 and rooms[r, c] != rooms[r, c+1]:
                draw.line((2+(c+1)*step, 2+r*step, 2+(c+1)*step, 2+(r+1)*step), fill='#141820', width=2)
            if r < 5 and rooms[r, c] != rooms[r+1, c]:
                draw.line((2+c*step, 2+(r+1)*step, 2+(c+1)*step, 2+(r+1)*step), fill='#141820', width=2)
    draw.rectangle((2, 2, SIDE+2, SIDE+2), outline='#141820', width=3)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chars', required=True, help='Experiment characters; never persisted inside Git')
    parser.add_argument('--font', type=Path, default=PRIVATE/'fonts/SourceHanSansSC-ExtraLight.otf')
    parser.add_argument('--output', type=Path, default=Path(os.environ.get('HANZI_FLOORPLAN_PRIVATE', PRIVATE))/'exports')
    parser.add_argument('--time-limit', type=float, default=10)
    args = parser.parse_args()
    output = private_path(args.output)
    chars = list(dict.fromkeys(args.chars.strip()))
    if not chars or len(chars) > 36:
        parser.error('Supply 1..36 unique characters')
    with TTFont(args.font) as font:
        cmap = font.getBestCmap()
        if any(ord(char) not in cmap for char in chars):
            parser.error('Font does not contain every requested character')
        family = font['name'].getDebugName(1)
    output.mkdir(parents=True, exist_ok=True)
    title_font = ImageFont.truetype(str(args.font), 30)
    small_font = ImageFont.truetype(str(args.font), 21)
    width, height = 780, 450
    gallery = Image.new('RGB', (width*2, 120+height*((len(chars)+1)//2)), '#f5f3ee')
    draw = ImageDraw.Draw(gallery)
    draw.text((28, 18), '汉字户型图 · 思源黑体 ExtraLight · 6 × 6', font=title_font, fill='#172434')
    draw.text((28, 65), '左：房间轮廓   右：字形叠加   灰格：未分配空白   实验结果，非正式题库', font=small_font, fill='#526170')
    records = []
    for index, char in enumerate(chars):
        labels, ink, roots, transform = glyph_placement(char, args.font)
        rooms, stats = allocate(ink, roots, args.time_limit)
        x, y = (index%2)*width+22, 120+(index//2)*height
        draw.text((x, y), f'{char}  ·  {stats["components"]} 个连通块', font=title_font, fill='#172434')
        gallery.paste(panel(labels, rooms, False), (x, y+45))
        gallery.paste(panel(labels, rooms, True), (x+380, y+45))
        draw.text((x, y+410), f'越界墨迹 {stats["outside_ink_fraction"]:.1%} · 空白 {stats["empty_cells"]} 格', font=small_font, fill='#526170')
        records.append({'character': char, 'rooms': rooms.tolist(), 'transform': transform, **stats})
    gallery.save(private_path(output/'contact-sheet.png'))
    metadata = {'font_family': family, 'font_sha256': hashlib.sha256(args.font.read_bytes()).hexdigest(),
                'raster_size': SIDE, 'threshold': 96, 'area_weight': .008, 'records': records}
    private_path(output/'private-report.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Generated {len(records)} private experiments: {output}')
    print(f'Mean outside-ink fraction: {np.mean([r["outside_ink_fraction"] for r in records]):.2%}')


if __name__ == '__main__':
    main()
