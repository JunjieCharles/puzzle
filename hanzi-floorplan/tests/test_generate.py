import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy import ndimage

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'generate.py'
spec = importlib.util.spec_from_file_location('floorplan', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GeneratorTests(unittest.TestCase):
    def test_shared_audit_rejects_private_floorplan_artifacts(self):
        audit_spec = importlib.util.spec_from_file_location(
            'floorplan_audit', module.ROOT/'word-kanji/scripts/audit_public.py')
        audit = importlib.util.module_from_spec(audit_spec)
        audit_spec.loader.exec_module(audit)
        self.assertTrue(audit.inspect_file('renamed/private-report.json', b'{}'))
        self.assertTrue(audit.inspect_file('contact-sheet.png', b''))
        self.assertTrue(audit.inspect_json({'records': [{'character': 'synthetic', 'rooms': []}]}))
        self.assertFalse(audit.inspect_json({'components': 3, 'empty_cells': 4}))

    def test_diagonal_ink_stays_connected(self):
        labels, count = module.components(np.eye(8, dtype=bool))
        self.assertEqual(count, 1)
        self.assertEqual(np.count_nonzero(labels), 8)

    def test_two_synthetic_components_keep_all_ink(self):
        ink = np.zeros((2, 36))
        ink[0, [0, 6, 12]] = 10
        ink[1, [23, 29, 35]] = 10
        rooms, stats = module.allocate(ink)
        self.assertEqual(stats['outside_ink_fraction'], 0)
        self.assertEqual(stats['empty_cells'], 30)
        for label in (1, 2):
            self.assertEqual(ndimage.label(rooms == label, module.CROSS)[1], 1)

    def test_flow_connects_separated_targets(self):
        ink = np.zeros((1, 36))
        ink[0, [0, 35]] = 10
        rooms, stats = module.allocate(ink)
        self.assertEqual(stats['outside_ink_fraction'], 0)
        self.assertEqual(np.count_nonzero(rooms), 11)
        self.assertEqual(ndimage.label(rooms == 1, module.CROSS)[1], 1)

    def test_competing_components_still_get_distinct_connected_rooms(self):
        ink = np.zeros((2, 36))
        ink[:, 14] = 10
        ink[0, 13] = 1
        ink[1, 15] = 1
        rooms, stats = module.allocate(ink)
        self.assertGreater(stats['outside_ink_fraction'], 0)
        for label in (1, 2):
            self.assertEqual(ndimage.label(rooms == label, module.CROSS)[1], 1)

    def test_repository_output_rejected(self):
        for path in (module.ROOT, module.ROOT/'hanzi-floorplan'/'exports',
                     module.ROOT/'..'/module.ROOT.name/'hidden'):
            with self.assertRaises(ValueError):
                module.private_path(path)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(module.private_path(folder), Path(folder).resolve())

    def test_empty_components_rejected(self):
        with self.assertRaises(ValueError):
            module.components(np.zeros((6, 6), dtype=bool))
        with self.assertRaises(ValueError):
            module.allocate(np.zeros((2, 36)))


if __name__ == '__main__':
    unittest.main()
