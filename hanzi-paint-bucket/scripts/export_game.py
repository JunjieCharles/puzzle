"""Export clues and user-authorized client-decryptable ciphertext."""
import argparse
import base64
from contextlib import closing
import json
import hashlib
from fractions import Fraction
from pathlib import Path
import secrets
import sqlite3
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from preview_bank import mask_png
from render_game_art import render_game_art

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PRIVATE = REPO.parent / 'puzzle-private/hanzi-paint-bucket'
TUTORIAL = '回答'


def export(banks, output, renderer=render_game_art, reset_progress=False):
    selected = {}
    for bank in banks:
        bank = bank.resolve()
        if bank == REPO or REPO in bank.parents or not bank.is_file():
            raise ValueError('Bank must exist outside repository')
        with closing(sqlite3.connect(bank.as_uri() + '?mode=ro', uri=True)) as db:
            has_metadata=db.execute("SELECT 1 FROM sqlite_master WHERE name='metadata'").fetchone()
            metadata=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0]) if has_metadata else {}
            if renderer is render_game_art:
                expected=hashlib.sha256((ROOT/'public/fonts/NotoSansSC-Thin.ttf').read_bytes()).hexdigest()
                if metadata.get('font')!='Noto Sans SC' or metadata.get('font_sha256')!=expected:
                    raise ValueError('Bank font must match the Noto Sans SC artwork renderer')
            area_difficulty=metadata.get('difficulty_aggregation')=='mean-paint-area-px-v1'
            metric='total_paint_area_px' if area_difficulty else 'stroke_ratio'
            for word, score in db.execute(f'SELECT word,{metric} FROM puzzles ORDER BY ordinal'):
                if area_difficulty:score=Fraction(score,len(word))
                if word == TUTORIAL or word in selected:
                    continue
                images = [mask_png(db.execute('SELECT mask_zlib FROM glyphs WHERE character=?', (c,)).fetchone()[0]) for c in word]
                selected[word] = (score, images)
    ordered = sorted(selected.items(), key=lambda item: (-item[1][0],item[0]))
    previous = None
    if not reset_progress and (output / 'levels.json').is_file():
        previous = json.loads((output / 'levels.json').read_text(encoding='utf-8'))
        old = previous.get('puzzles', [])
        # Preserve player progress only when every clue and answer still matches in order.
        try:
            old_cipher = AESGCM(base64.b64decode(previous['encryption']['key'], validate=True))
            unchanged = len(old) == len(ordered) and all(
                item.get('images') == images and previous_word(old_cipher.decrypt(
                    base64.b64decode(item['sealed']['iv'], validate=True),
                    base64.b64decode(item['sealed']['ciphertext'], validate=True),
                    item['id'].encode()), previous['version']) == word
                for item, (word, (_, images)) in zip(old, ordered)
            )
        except (KeyError, ValueError, TypeError, InvalidTag):
            unchanged = False
        if not unchanged:
            previous = None
    records = []
    art = renderer([word for word, _ in ordered] + [TUTORIAL])
    key = AESGCM.generate_key(bit_length=256)
    cipher = AESGCM(key)
    encode = lambda raw: base64.b64encode(raw).decode('ascii')
    for index, (word, (_, images)) in enumerate(ordered):
        prior = previous['puzzles'][index] if previous else {}
        public_id = prior.get('id', secrets.token_hex(16))
        iv = secrets.token_bytes(12)
        content = json.dumps({'word': word, 'strokes': [art[c]['strokes'] for c in word]}, ensure_ascii=False, separators=(',', ':')).encode()
        encrypted = cipher.encrypt(iv, zlib.compress(content, 9), public_id.encode())
        records.append({'id': public_id, 'images': images,
                        'sealed': {'iv': encode(iv), 'ciphertext': encode(encrypted)}})
    if not records:
        raise ValueError('Empty bank')
    payload = {'version': 'paint-v4', 'revision': previous['revision'] if previous else secrets.token_hex(8),
               'encryption': {'algorithm': 'AES-GCM', 'key': encode(key)}, 'puzzles': records}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'levels.json').write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    (output / 'tutorial.json').write_text(json.dumps({'paint':[art[c]['paint'] for c in TUTORIAL], 'strokes':[art[c]['strokes'] for c in TUTORIAL]}, separators=(',', ':')), encoding='utf-8')
    print(f'Exported {len(records)} encrypted levels; tutorial excluded; progress revision {"preserved" if previous else "new"}.')


def previous_word(content, version):
    text = (zlib.decompress(content) if version == 'paint-v4' else content).decode()
    return json.loads(text)['word'] if version == 'paint-v4' else text


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, action='append')
    parser.add_argument('--reset-progress', action='store_true', help='Start a new progress revision even when the question content is unchanged')
    args = parser.parse_args()
    export(args.bank or [PRIVATE / 'hsk-combined-editorial-v23-noto-bank/bank.sqlite'], ROOT / 'public', reset_progress=args.reset_progress)
    from build_game_assets import build_game_assets
    build_game_assets()
