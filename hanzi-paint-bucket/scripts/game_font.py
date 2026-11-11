"""Current puzzle font; historical analyses keep their own pinned fonts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY = 'Source Han Sans CN'
STYLE = 'Light'
WEIGHT = 300
FILE = ROOT / 'public/fonts/SourceHanSansCN-Light.otf'
