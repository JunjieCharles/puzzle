"""Synthetic geometry only; no real question fixtures."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_rectangle_similarity import rectangle_signature, rectangle_iou, rectangle_center_distance


class RectangleSimilarityTests(unittest.TestCase):
    def test_whole_group_stretch_preserves_signature(self):
        a = np.zeros((100, 100), dtype=bool)
        a[10:30, 10:30] = True
        a[40:60, 10:30] = True
        b = np.zeros_like(a)
        b[20:40, 20:80] = True
        b[50:70, 20:80] = True
        self.assertAlmostEqual(rectangle_iou(rectangle_signature(a), rectangle_signature(b)), 1)

    def test_internal_proportions_are_not_normalized_individually(self):
        a = np.array([[0, 0, 1, .4], [0, .6, 1, 1]])
        b = np.array([[0, 0, 1, .2], [0, .6, 1, 1]])
        self.assertAlmostEqual(rectangle_iou(a, b), .75)
        self.assertAlmostEqual(rectangle_iou(a, b[::-1]), .75)

    def test_count_and_topology_must_match(self):
        a = np.array([[0, 0, 1, .4], [0, .6, 1, 1]])
        b = np.array([[0, 0, .4, 1], [.6, 0, 1, 1]])
        self.assertEqual(rectangle_iou(a, b), 0)
        self.assertEqual(rectangle_iou(a, b[:1]), 0)

    def test_empty_and_nonrectangle_excluded(self):
        a = np.zeros((100, 100), dtype=bool)
        self.assertIsNone(rectangle_signature(a))
        a[10:30, 10:30] = True
        a[20:30, 20:30] = False
        self.assertIsNone(rectangle_signature(a))

    def test_original_position_survives_structure_normalization(self):
        a = np.zeros((200, 200), dtype=bool)
        a[10:30, 10:30] = True
        a[40:60, 10:30] = True
        b = np.roll(a, (100, 50), axis=(0, 1))
        self.assertEqual(rectangle_iou(rectangle_signature(a), rectangle_signature(b)), 1)
        self.assertEqual(rectangle_center_distance(rectangle_signature(a, False), rectangle_signature(b, False)), 150)

    def test_position_threshold_uses_half_pixel_centers(self):
        a = np.array([[0, 0, 10, 10]], dtype=float)
        b = np.array([[30, 0, 41, 10]], dtype=float)
        self.assertEqual(rectangle_center_distance(a, b), 30.5)
        self.assertGreater(rectangle_center_distance(a, b), 30)
        self.assertLessEqual(rectangle_center_distance(a, b), 40)


if __name__ == '__main__':
    unittest.main()
