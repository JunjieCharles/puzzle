"""Losslessly compress public encrypted game data without modifying fonts."""
import gzip
from pathlib import Path
PUBLIC = Path(__file__).resolve().parents[1] / 'public'

def build_game_assets(public=PUBLIC):
    packed = gzip.compress((public / 'levels.json').read_bytes(), compresslevel=9, mtime=0)
    (public / 'levels.json.gz').write_bytes(packed)
    ui_bytes=sum(p.stat().st_size for p in (public/'fonts').glob('PaintBucketUI-*.woff2'))
    print(f'Compressed bank: {len(packed)} bytes; interface font download: {ui_bytes} bytes; puzzle font download: 0 bytes.')

if __name__ == '__main__':
    build_game_assets()
