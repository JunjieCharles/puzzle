import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_site import ASSETS, build_site


class BuildSiteTests(unittest.TestCase):
    def test_both_pages_bases_publish_only_public_assets(self):
        for base, relative in (("", "puzzle/word-kanji"), ("/puzzle", "word-kanji")):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "site"
                target = build_site(output, base)
                self.assertEqual(target, output / relative)
                files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
                self.assertEqual(files, {"index.html"} | {f"{relative}/{name}" for name in ASSETS})
                self.assertIn(f'./{relative}/', (output / "index.html").read_text(encoding="utf-8"))
                with self.assertRaises(ValueError):
                    build_site(output, base)

    def test_wrong_project_base_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                build_site(Path(folder) / "site", "/another-project")
