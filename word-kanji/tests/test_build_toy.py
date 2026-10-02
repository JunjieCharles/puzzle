import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_toy import build_toy


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
            self.assertIn("toy-sdk.js", html)
            for name in ("campaign.json", "campaign-two.json", "hsk-two-words.json"):
                self.assertEqual((target / name).read_bytes(), (ROOT / "public" / name).read_bytes())
            with self.assertRaises(ValueError):
                build_toy(directory)


if __name__ == "__main__":
    unittest.main()
