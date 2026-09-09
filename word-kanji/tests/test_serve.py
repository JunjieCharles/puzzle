"""Check that virtual website paths cannot expose project sources."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("site_serve", Path(__file__).resolve().parents[1] / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class PublicPathTests(unittest.TestCase):
    def test_browser_assets_ignore_windows_file_associations(self):
        from unittest.mock import patch
        handler = object.__new__(serve.PublicHandler)
        with patch("mimetypes.guess_type", return_value=("text/plain", None)):
            self.assertEqual(handler.guess_type("app.js"), "text/javascript")
            self.assertEqual(handler.guess_type("coin.svg"), "image/svg+xml")

    def test_only_public_subdirectories_are_mapped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "sample"
            public = root / "public"
            public.mkdir(parents=True)
            self.assertEqual(serve.public_path("/puzzle/sample", root), public)
            self.assertEqual(serve.public_path("/puzzle/sample/app.js?v=1", root), public / "app.js")
            for url in ("/", "/sample/public/app.js", "/AGENTS.md", "/puzzle/absent/",
                        "/puzzle/sample/../source.py", "/puzzle/sample/%2e%2e/source.py",
                        "/puzzle/sample/..%5csource.py", "/puzzle/sample/C:/secret"):
                self.assertIsNone(serve.public_path(url, root))


if __name__ == "__main__":
    unittest.main()
