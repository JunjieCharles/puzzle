import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('analysis', Path(__file__).resolve().parents[1]/'scripts/analyze_hsk.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class AnalysisTests(unittest.TestCase):
    def test_pruned_pairs_match_full_pixel_comparison(self):
        rng = np.random.default_rng(12)
        masks = []
        base = np.zeros((480,480), dtype=bool)
        base[150:300, 120:280] = True
        masks.extend([base, base.copy(), np.roll(base,1,axis=0), np.roll(base,20,axis=1)])
        for _ in range(8):
            mask = base.copy()
            y = rng.integers(140,310,500); x = rng.integers(110,290,500)
            mask[y,x] = ~mask[y,x]
            masks.append(mask)
        expected = {}
        for i in range(len(masks)):
            for j in range(i+1,len(masks)):
                distance = np.logical_xor(masks[i],masks[j]).sum()/np.logical_or(masks[i],masks[j]).sum()
                if distance <= .1:
                    expected[i,j] = distance
        actual = {(i,j):d for i,j,d in analysis.close_pairs(masks,np.array([m.sum() for m in masks]))}
        self.assertEqual(actual.keys(), expected.keys())
        for pair in actual:
            self.assertAlmostEqual(actual[pair],expected[pair])

    def test_word_ambiguity_requires_every_position_and_same_length(self):
        rows = analysis.ambiguity(['a','b','c'], [(0,1,0),(1,2,.05)], ['a','b','c','aa','ab','ac','cc'])
        self.assertEqual(rows[0]['word_pairs'],2)
        self.assertEqual(rows[0]['ambiguous_words'],4)
        self.assertEqual(rows[3]['word_pairs'],4)

    def test_repository_output_rejected(self):
        with self.assertRaises(ValueError):
            analysis.private_path(analysis.REPO/'output')


if __name__ == '__main__':
    unittest.main()
