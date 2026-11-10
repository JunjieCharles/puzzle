import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('font_components',Path(__file__).resolve().parents[1]/'scripts/analyze_font_components.py')
components=importlib.util.module_from_spec(spec);spec.loader.exec_module(components)


class ComponentTests(unittest.TestCase):
    def test_noise_and_exact_threshold(self):
        areas=[[100,1],[100,24],[100],[100,4,3],[100,2],[100,20]]
        counts=[sum(a>=25 for a in values) for values in areas]
        self.assertFalse(components.inconsistent(counts))
        areas[0].append(25)
        self.assertTrue(components.inconsistent([sum(a>=25 for a in v) for v in areas]))

    def test_empty_vs_painted_and_missing_font(self):
        self.assertFalse(components.inconsistent([0]*6))
        self.assertTrue(components.inconsistent([0,0,0,0,0,1]))
        self.assertFalse(components.inconsistent([None,0,0,0,0,1]))


if __name__=='__main__':unittest.main()
