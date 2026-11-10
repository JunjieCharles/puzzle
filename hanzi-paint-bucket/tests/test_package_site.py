import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_site import ASSETS, package_site


class PackageTests(unittest.TestCase):
    def test_bases_and_exact_allowlist_preserve_other_projects(self):
        for base, relative in [('', 'puzzle/hanzi-paint-bucket'), ('/puzzle', 'hanzi-paint-bucket')]:
            with self.subTest(base=base), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'index.html').write_text('existing site', encoding='utf-8')
                target = package_site(root, base)
                self.assertEqual(target, root / relative)
                self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, set(ASSETS))
                self.assertEqual((root / 'index.html').read_text(encoding='utf-8'), 'existing site')
                with self.assertRaises(ValueError): package_site(root, base)
