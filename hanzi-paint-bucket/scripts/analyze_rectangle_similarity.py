"""Offline rectangle-structure experiment; detailed results stay outside the repo."""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import zlib

import numpy as np
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

from build_hsk_bank import is_single_solid_rectangle
from build_idiom_bank import alternative_matches, private_path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT.parent.parent / 'puzzle-private/hanzi-paint-bucket'


def rectangle_signature(mask, normalize=True):
    """Normalize the union bbox, retaining internal gaps and relative sizes."""
    labels, _ = ndimage.label(mask)
    boxes = []
    for label, slices in enumerate(ndimage.find_objects(labels), 1):
        region = labels[slices] == label
        if region.sum() < 25:
            continue
        if not is_single_solid_rectangle(region, minimum_fill=.99):
            return None
        y, x = slices
        boxes.append((x.start, y.start, x.stop, y.stop))
    if not boxes:
        return None
    boxes = np.array(boxes, dtype=float)
    if not normalize:
        return boxes
    low = boxes[:, :2].min(axis=0)
    size = boxes[:, 2:].max(axis=0) - low
    return (boxes - np.tile(low, 2)) / np.tile(size, 2)


def rectangle_center_distance(a, b):
    """L1 distance between group bounding-box centers in original canvas pixels."""
    if a is None or b is None:
        return float('inf')
    center_a = (a[:, :2].min(axis=0) + a[:, 2:].max(axis=0)) / 2
    center_b = (b[:, :2].min(axis=0) + b[:, 2:].max(axis=0)) / 2
    return float(np.abs(center_a-center_b).sum())


def rectangle_iou(a, b):
    """Exact continuous rectangle-union IoU; require matched layout topology."""
    if a is None or b is None or len(a) != len(b):
        return 0.
    lengths = np.maximum(0, np.minimum(a[:, None, 2:], b[None, :, 2:])
                         - np.maximum(a[:, None, :2], b[None, :, :2]))
    intersections = lengths.prod(axis=2)
    rows, cols = linear_sum_assignment(-intersections)
    matched = b[cols[np.argsort(rows)]]
    # Preserve left/right and above/below separation for every matched pair.
    for axis in (0, 1):
        relation = a[:, None, axis + 2] <= a[None, :, axis] + 1e-12
        other_relation = matched[:, None, axis + 2] <= matched[None, :, axis] + 1e-12
        if not np.array_equal(relation, other_relation):
            return 0.
    intersection = intersections.sum()
    union = np.prod(a[:, 2:] - a[:, :2], axis=1).sum() + np.prod(b[:, 2:] - b[:, :2], axis=1).sum() - intersection
    return float(intersection / union)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, default=PRIVATE/'hsk-combined-editorial-v23-noto-bank/bank.sqlite')
    parser.add_argument('--output', type=Path, default=PRIVATE/'rectangle-similarity-v23')
    args = parser.parse_args()
    hsk = {r['word'] for r in json.loads((ROOT.parent/'word-kanji/data/hsk-2025.json').read_text(encoding='utf-8'))['words']}
    output = private_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.bank.resolve().as_uri()+'?mode=ro', uri=True) as db:
        targets = [r[0] for r in db.execute('SELECT word FROM puzzles ORDER BY ordinal')]
        competitors = [r[0] for r in db.execute('SELECT word FROM comparison_words')]
        old_pairs = list(db.execute('SELECT character_a,character_b FROM similar_pairs'))
        meta = json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
    assert meta['font_sha256'] == hashlib.sha256((ROOT/'public/fonts/NotoSansSC-Thin.ttf').read_bytes()).hexdigest()
    areas, signatures = {}, {}
    with sqlite3.connect((args.bank.parent/'measurements.sqlite').resolve().as_uri()+'?mode=ro', uri=True) as db:
        for c, area, packed in db.execute('SELECT character,area_px,mask_zlib FROM characters'):
            areas[c] = area
            mask = np.unpackbits(np.frombuffer(zlib.decompress(packed), dtype=np.uint8)).reshape(480, 480).astype(bool)
            signature = rectangle_signature(mask)
            if signature is not None:
                signatures[c] = signature
    words, baseline = alternative_matches(competitors, targets, areas, old_pairs)
    assert all(len(matches) == 1 for matches in baseline.values()), 'Current bank baseline is not unique'
    query = set(''.join(targets)) & signatures.keys()
    scores = {}
    for a in sorted(query):
        for b in signatures:
            if a == b or (b in query and b < a):
                continue
            score = rectangle_iou(signatures[a], signatures[b])
            if score > .8:
                scores[tuple(sorted((a, b)))] = score
    details, summary = [], {'questions': len(targets), 'comparison_words': len(competitors),
                           'rectangle_characters': len(signatures), 'query_rectangle_characters': len(query),
                           'threshold_comparison': 'strict >', 'settings': []}
    for threshold in (.80, .85, .90, .95, .98):
        added = [pair for pair, score in scores.items() if score > threshold]
        _, matches = alternative_matches(competitors, targets, areas, old_pairs + added)
        affected = []
        for word in targets:
            alternatives = [words[i] for i in matches[word] if words[i] != word]
            if alternatives:
                evidence = []
                for alternative in alternatives:
                    changes = [{'a': a, 'b': b, 'rectangle_iou': scores.get(tuple(sorted((a, b)))),
                                'existing_pixel_match': (a, b) in old_pairs or (b, a) in old_pairs,
                                'blank_match': areas[a] == areas[b] == 0}
                               for a, b in zip(word, alternative) if a != b]
                    evidence.append({'alternative': alternative, 'in_hsk': alternative in hsk, 'changes': changes})
                affected.append({'word': word, 'alternatives': evidence})
        details.append({'threshold': threshold, 'affected': affected})
        summary['settings'].append({'threshold': threshold, 'affected': len(affected),
                                    'by_length': dict(Counter(len(r['word']) for r in affected)),
                                    'with_hsk_alternative': sum(any(a['in_hsk'] for a in r['alternatives']) for r in affected),
                                    'remaining_without_refill': len(targets)-len(affected)})
    (output/'details.json').write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    sections = []
    for setting in reversed(details):
        rows = []
        for row in sorted(setting['affected'], key=lambda r: not any(a['in_hsk'] for a in r['alternatives'])):
            alternatives = []
            for alt in row['alternatives']:
                changes = ', '.join(html.escape(c['a']+'↔'+c['b']) +
                                    (f" {c['rectangle_iou']:.2%}" if c['rectangle_iou'] is not None else '（原规则）')
                                    for c in alt['changes'])
                alternatives.append(html.escape(alt['alternative'])+('【HSK】' if alt['in_hsk'] else '【扩展词库】')+'：'+changes)
            rows.append('<tr><td>'+html.escape(row['word'])+'</td><td>'+'<br>'.join(alternatives)+'</td></tr>')
        sections.append(f"<h2 id=\"t{round(setting['threshold']*100)}\">归一化矩形 IoU &gt; {setting['threshold']:.0%}：{len(rows)} 题</h2><table><tr><th>当前题目</th><th>替代词及变化字</th></tr>"+''.join(rows)+'</table>')
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>矩形结构相似度试验</title><style>body{font:16px/1.7 sans-serif;max-width:1100px;margin:30px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}</style><h1>矩形结构相似度：离线试验</h1><p>当前 212 题；保留像素规则。忽略小于25px的连通块，剩余色块均须满足99%矩形填充率及边缘约束；矩形数相同、整体横纵独立归一化、上下左右分离关系一致。没有更改题库或补题。</p>'+''.join(sections), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
