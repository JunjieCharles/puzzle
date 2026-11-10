"""Synthetic private data only; temporary files are outside the repository."""
import contextlib
import base64
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_game import export, TUTORIAL
spec = importlib.util.spec_from_file_location('paint_audit', ROOT.parent / 'word-kanji/scripts/audit_public.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ExportTests(unittest.TestCase):
    def test_whitelist_checks_and_tutorial_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bank = root / 'bank.sqlite'
            # Artificial solid binary masks, deliberately unrelated to real glyphs.
            with sqlite3.connect(bank) as db:
                db.executescript('CREATE TABLE puzzles(word TEXT,stroke_ratio REAL,ordinal INTEGER); CREATE TABLE glyphs(character TEXT,mask_zlib BLOB); CREATE TABLE comparison_words(word TEXT);')
                for i, word in enumerate(['甲乙', TUTORIAL]):
                    db.execute('INSERT INTO puzzles VALUES (?,?,?)',(word,1-i/10,i))
                    db.execute('INSERT INTO comparison_words VALUES (?)',(word,))
                    for c in word: db.execute('INSERT INTO glyphs VALUES (?,?)',(c,zlib.compress(b'\xff'*(480*480//8))))
                db.execute('INSERT INTO comparison_words VALUES (?)',('丙丁',))
            db.close()
            with contextlib.redirect_stdout(io.StringIO()): export([bank],root/'out')
            raw=(root/'out/levels.json').read_text(encoding='utf-8')
            data=json.loads(raw)
            self.assertEqual(len(data['puzzles']),1)
            self.assertEqual(audit.inspect_paint_campaign(data),[])
            item=data['puzzles'][0]
            self.assertEqual(set(item),{'id','images','sealed'})
            self.assertNotIn('甲乙',raw)
            cipher=AESGCM(base64.b64decode(data['encryption']['key']))
            self.assertEqual(cipher.decrypt(base64.b64decode(item['sealed']['iv']),base64.b64decode(item['sealed']['ciphertext']),item['id'].encode()).decode(),'甲乙')
            self.assertFalse((root/'out/vocabulary.json').exists())
            with contextlib.redirect_stdout(io.StringIO()): export([bank],root/'out')
            again=json.loads((root/'out/levels.json').read_text(encoding='utf-8'))
            self.assertEqual(again['revision'],data['revision'])
            self.assertEqual(again['puzzles'][0]['id'],item['id'])
            self.assertNotEqual(again['puzzles'][0]['sealed'],item['sealed'])
            item['character']='甲'
            self.assertTrue(audit.inspect_paint_campaign(data))

    def test_reject_repository_private_input(self):
        with self.assertRaises(ValueError): export([ROOT/'fake.sqlite'],ROOT/'public')
