import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('strokes',Path(__file__).resolve().parents[1]/'scripts/analyze_strokes.py')
strokes=importlib.util.module_from_spec(spec);spec.loader.exec_module(strokes)


class StrokeTests(unittest.TestCase):
    def test_enclosure_is_explained_but_distant_ink_is_not(self):
        ink=np.zeros((100,100),bool);ink[20:80,20:80]=True;ink[24:76,24:76]=False
        paint=np.zeros_like(ink);paint[24:76,24:76]=True
        ink[4:8,20:80]=True
        result=strokes.implied_ink(ink,paint)
        self.assertFalse(result[4:8].any())
        self.assertTrue(result[40:60,20:24].all())
        self.assertTrue(result[40:60,76:80].all())
        self.assertFalse((result & ~ink).any())
        self.assertGreater(result.sum()/ink[20:80].sum(),.9)

    def test_empty_paint_and_overlap(self):
        ink=np.zeros((20,20),bool);ink[4:8,4:8]=True
        self.assertFalse(strokes.implied_ink(ink,np.zeros_like(ink)).any())
        with self.assertRaises(ValueError):strokes.implied_ink(ink,ink)
