import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_toy import build_toy
from vocabulary_policy import REVISION, filter_endless, filter_words
import json
import hashlib


class ToyBuildTests(unittest.TestCase):
    def test_separate_package_without_save_code(self):
        with tempfile.TemporaryDirectory() as directory:
            target = build_toy(directory)
            names = {p.name for p in target.iterdir()}
            self.assertNotIn("save-code.js", names)
            html = (target / "index.html").read_text(encoding="utf-8")
            app = (target / "app.js").read_text(encoding="utf-8")
            self.assertNotIn('id="save-open"', html)
            self.assertNotIn('id="save-dialog"', html)
            self.assertNotIn("encodeSave", app)
            self.assertNotIn("decodeSave", app)
            self.assertIn('id="rank-two"', html)
            for name in ("rank-endless-one", "rank-endless-two"):
                self.assertIn(f'id="{name}"', html)
            self.assertNotIn('!platform && ["endless', app)
            for name in ("endless.js",):
                self.assertEqual((target / name).read_bytes(), (ROOT / "public" / name).read_bytes())
            vocabulary = json.loads((ROOT / "public/endless-lexicon.json").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((target / "endless-lexicon.json").read_text(encoding="utf-8")), filter_endless(vocabulary))
            self.assertIn(REVISION, (target / "endless-engine.js").read_text(encoding="utf-8"))
            self.assertIn(hashlib.sha256((target / "endless-lexicon.json").read_bytes()).hexdigest(),
                          (target / "endless-worker.js").read_text(encoding="utf-8"))
            self.assertIn("toy-sdk.js", html)
            for name in ("campaign.json", "campaign-two.json"):
                original = json.loads((ROOT / "public" / name).read_text(encoding="utf-8"))
                result = json.loads((target / name).read_text(encoding="utf-8"))
                self.assertTrue(all(p in original["puzzles"] for p in result["puzzles"]))
                if len(result["puzzles"]) != len(original["puzzles"]):
                    self.assertNotEqual(result["revision"], original["revision"])
            hints = json.loads((ROOT / "public/hsk-two-words.json").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((target / "hsk-two-words.json").read_text(encoding="utf-8"))["words"], filter_words(hints["words"]))
            with self.assertRaises(ValueError):
                build_toy(directory)


if __name__ == "__main__":
    unittest.main()
