"""Check that virtual website paths cannot expose project sources."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("site_serve", Path(__file__).resolve().parents[1] / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class PublicPathTests(unittest.TestCase):
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
