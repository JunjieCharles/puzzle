import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.export_endless_lexicon import payload
from scripts.audit_public import inspect_file, inspect_json


class EndlessTests(unittest.TestCase):
    def test_generic_export_and_boundary(self):
        path = ROOT / "public" / "endless-lexicon.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload())
        self.assertEqual(inspect_file(path.name, path.read_bytes()), [])
        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), (ROOT / "public" / "endless-worker.js").read_text(encoding="utf-8"))
        bad = payload()
        bad["common"] = bad["common"][:-1]
        self.assertTrue(inspect_file(path.name, json.dumps(bad).encode()))
        self.assertTrue(inspect_json({"solution": "synthetic"}))
        self.assertTrue(inspect_json({"cooling_state": []}))

    @unittest.skipUnless(shutil.which("node"), "Node.js required for browser engine unit tests")
    def test_browser_engine_and_progress(self):
        result = subprocess.run(["node", "--experimental-default-type=module", str(ROOT / "tests" / "endless.mjs")],
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
