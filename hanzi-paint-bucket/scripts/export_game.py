"""Export clues and user-authorized client-decryptable ciphertext."""
import argparse
import base64
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from preview_bank import mask_png

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PRIVATE = REPO.parent / 'puzzle-private/hanzi-paint-bucket'
TUTORIAL = '回答'


def export(banks, output):
    selected = {}
    for bank in banks:
        bank = bank.resolve()
        if bank == REPO or REPO in bank.parents or not bank.is_file():
            raise ValueError('Bank must exist outside repository')
        with closing(sqlite3.connect(bank.as_uri() + '?mode=ro', uri=True)) as db:
            for word, score in db.execute('SELECT word,stroke_ratio FROM puzzles ORDER BY ordinal'):
                if word == TUTORIAL or word in selected:
                    continue
                images = [mask_png(db.execute('SELECT mask_zlib FROM glyphs WHERE character=?', (c,)).fetchone()[0]) for c in word]
                selected[word] = (score, images)
    ordered = sorted(selected.items(), key=lambda item: -item[1][0])
    previous = None
    if (output / 'levels.json').is_file():
        previous = json.loads((output / 'levels.json').read_text(encoding='utf-8'))
        old = previous.get('puzzles', [])
        # Preserve player progress only when every clue and answer still matches in order.
        try:
            old_cipher = AESGCM(base64.b64decode(previous['encryption']['key'], validate=True))
            unchanged = len(old) == len(ordered) and all(
                item.get('images') == images and old_cipher.decrypt(
                    base64.b64decode(item['sealed']['iv'], validate=True),
                    base64.b64decode(item['sealed']['ciphertext'], validate=True),
                    item['id'].encode()) == word.encode()
                for item, (word, (_, images)) in zip(old, ordered)
            )
        except (KeyError, ValueError, TypeError, InvalidTag):
            unchanged = False
        if not unchanged:
            previous = None
    records = []
    key = AESGCM.generate_key(bit_length=256)
    cipher = AESGCM(key)
    encode = lambda raw: base64.b64encode(raw).decode('ascii')
    for index, (word, (_, images)) in enumerate(ordered):
        prior = previous['puzzles'][index] if previous else {}
        public_id = prior.get('id', secrets.token_hex(16))
        iv = secrets.token_bytes(12)
        encrypted = cipher.encrypt(iv, word.encode(), public_id.encode())
        records.append({'id': public_id, 'images': images,
                        'sealed': {'iv': encode(iv), 'ciphertext': encode(encrypted)}})
    if not records:
        raise ValueError('Empty bank')
    payload = {'version': 'paint-v3', 'revision': previous['revision'] if previous else secrets.token_hex(8),
               'encryption': {'algorithm': 'AES-GCM', 'key': encode(key)}, 'puzzles': records}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'levels.json').write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    print(f'Exported {len(records)} encrypted levels; tutorial excluded; progress revision {"preserved" if previous else "new"}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, action='append')
    args = parser.parse_args()
    export(args.bank or [PRIVATE / 'hsk-combined-editorial-v12-bank/bank.sqlite'], ROOT / 'public')
