"""Export generic font coverage, never a puzzle or answer selection."""
import json
from pathlib import Path
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
with TTFont(ROOT/'public/fonts/NotoSansSC-Thin.ttf') as font:
    points = sorted(font.getBestCmap())
ranges = []
for point in points:
    if ranges and point == ranges[-1][1]+1:
        ranges[-1][1] = point
    else:
        ranges.append([point,point])
(ROOT/'public/font-coverage.mjs').write_text(
    '// Generic Unicode coverage of the bundled font. Regenerate with scripts/font_coverage.py.\n'
    + 'export const ranges = '+json.dumps(ranges,separators=(',',':'))+';\n',encoding='utf-8')
