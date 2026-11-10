"""Add only the paint game's reviewed public assets to a Pages artifact."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'word-kanji/scripts'))
from audit_public import inspect_file

ASSETS = ('index.html', 'style.css', 'bucket.svg', 'game.mjs', 'decrypt.mjs',
          'state.mjs', 'glyph.mjs', 'fill.mjs', 'levels.json',
          'fonts/HarmonyOS_Sans_SC_Thin.woff2', 'fonts/LICENSE-HarmonyOS-Sans.txt')


def package_site(output, base_path=''):
    base_path = base_path.rstrip('/')
    if base_path not in ('', '/puzzle'):
        raise ValueError('Unsupported Pages base path')
    target = Path(output).resolve() / (Path('hanzi-paint-bucket') if base_path else Path('puzzle/hanzi-paint-bucket'))
    if target.exists():
        raise ValueError('Refusing to overwrite an existing project directory')
    for name in ASSETS:
        source = ROOT / 'public' / name
        if source.is_symlink() or not source.is_file() or inspect_file('hanzi-paint-bucket/public/' + name, source.read_bytes()):
            raise ValueError(f'Invalid game asset: {name}')
    for name in ASSETS:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'public' / name, destination)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-path', default='')
    args = parser.parse_args()
    print(package_site(args.output, args.base_path))
