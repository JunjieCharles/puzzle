"""Render private font comparisons; never write specimen mappings in the repo."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parents[2]
COLORS = ['#f5b942', '#49b9ae', '#f18d83', '#8d9ee0', '#b8ce68', '#be8cbf']


def glyph_layers(char, path, side=480):
    font = ImageFont.truetype(str(path), 400)
    try:
        font.set_variation_by_axes([a['minimum'] for a in font.get_variation_axes()])
    except OSError:
        pass  # Static Thin font.
    ink = Image.new('L', (side, side))
    draw = ImageDraw.Draw(ink)
    left, top, right, bottom = draw.textbbox((0, 0), char, font=font)
    draw.text(((side-right-left)/2, (side-bottom-top)/2), char, font=font, fill=255)
    barrier = np.asarray(ink) >= 128
    holes = ndimage.binary_fill_holes(barrier) & ~barrier
    labels, count = ndimage.label(holes)
    paint = Image.new('RGB', ink.size, 'white')
    for i in range(1, count + 1):
        mask = Image.fromarray(np.uint8(labels == i) * 255)
        paint.paste(COLORS[(i-1) % len(COLORS)], mask=mask)
    outlined = paint.copy()
    outlined.paste('#253344', mask=ink)
    return outlined, paint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chars', required=True)
    parser.add_argument('--harmony', type=Path, default=REPO/'hanzi-paint-bucket/public/fonts/HarmonyOS_Sans_SC_Thin.ttf')
    parser.add_argument('--output', type=Path, default=REPO.parent / 'puzzle-private' / 'hanzi-paint-bucket')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == REPO or REPO in output.parents:
        parser.error('Specimens must be written outside the repository.')
    chars = list(dict.fromkeys(c for c in args.chars if not c.isspace()))
    if not 1 <= len(chars) <= 10:
        parser.error('Provide 1–10 distinct characters.')
    families = [('HarmonyOS Sans SC', args.harmony)]
    for _, path in families:
        with TTFont(path) as font:
            if any(ord(c) not in font.getBestCmap() for c in chars):
                parser.error('A selected font lacks a requested glyph.')
    label = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 22)
    title = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 38)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
    width = max(1100, 270 + len(chars)*170)
    sheet = Image.new('RGB', (width, 170+330*len(families)), '#f4f2ed')
    draw = ImageDraw.Draw(sheet)
    draw.text((40, 28), '汉字油漆桶 / HarmonyOS Sans SC Thin', font=title, fill='#253344')
    draw.text((42, 88), '同字号 · 真实字体轮廓 · 只填闭合空白区域', font=small, fill='#62707a')
    for row, (name, path) in enumerate(families):
        y = 145 + row*330
        draw.rounded_rectangle((25, y, width-25, y+312), radius=18, fill='white')
        draw.text((45, y+28), name, font=label, fill='#253344')
        draw.text((45, y+65), 'Thin / 最细字重', font=small, fill='#62707a')
        draw.text((45, y+115), '笔画 + 填色 →', font=small, fill='#62707a')
        draw.text((45, y+240), '仅填色区域 →', font=small, fill='#62707a')
        for col, char in enumerate(chars):
            outlined, paint = glyph_layers(char, path)
            x = 260 + col*170
            for layer, offset in [(outlined, 10), (paint, 160)]:
                sheet.paste(layer.resize((145, 145), Image.Resampling.LANCZOS), (x, y+offset))
    output.mkdir(parents=True, exist_ok=True)
    sheet.save(output / 'font-comparison.png')
    print('Saved private specimen:', output / 'font-comparison.png')


if __name__ == '__main__':
    main()
