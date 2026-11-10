import importlib.util
from pathlib import Path
import unittest
import zlib

import numpy as np

spec=importlib.util.spec_from_file_location('shift',Path(__file__).resolve().parents[1]/'scripts/analyze_shift_similarity.py')
shift=importlib.util.module_from_spec(spec);spec.loader.exec_module(shift)


class ShiftTests(unittest.TestCase):
    def test_translation_without_clipping(self):
        a=np.zeros((30,30),bool);a[1:5,2:7]=True
        b=np.zeros_like(a);b[11:15,9:14]=True
        inter,union,distance,dx,dy=shift.best_translation(a,b)
        self.assertEqual((inter,union,distance,dx,dy),(20,20,17,-7,-10))

    def test_global_maximum_not_nearby_good_enough(self):
        a=np.zeros((40,40),bool);a[10:30,5:25]=True
        b=np.zeros_like(a);b[10:30,8:28]=True
        inter,union,distance,_,_=shift.best_translation(a,b)
        self.assertEqual((inter,union,distance),(400,400,3))
        # Near zero can have high IoU, but cannot replace the global maximizer.
        self.assertFalse(distance<3)

    def test_tied_maxima_choose_nearest(self):
        a=np.zeros((12,12),bool);a[3:9,3:9]=True
        b=np.zeros_like(a);b[5:7,5:7]=True
        self.assertEqual(shift.best_translation(a,b)[:3],(4,36,0))

    def test_random_small_masks_match_exhaustive(self):
        rng=np.random.default_rng(12)
        for _ in range(12):
            a=rng.random((7,7))<.3;b=rng.random((7,7))<.3
            best=-1;nearest=100
            for dy in range(-6,7):
                for dx in range(-6,7):
                    n=sum(bool(a[y,x] and b[y-dy,x-dx]) for y in range(7) for x in range(7) if 0<=y-dy<7 and 0<=x-dx<7)
                    if n>best:best=n;nearest=abs(dx)+abs(dy)
                    elif n==best:nearest=min(nearest,abs(dx)+abs(dy))
            self.assertEqual(shift.best_translation(a,b)[:3],(best,int(a.sum()+b.sum())-best,nearest))

    def test_pruning_retains_close_shifts_and_rejects_distant(self):
        base=np.zeros((480,480),bool);base[150:190,100:140]=True
        masks={'a':base,'b':np.roll(base,3,axis=1),'c':np.roll(base,30,axis=1)}
        glyphs={c:('font',c,1,int(m.sum()),0,0,'[]','[]',zlib.compress(np.packbits(m).tobytes())) for c,m in masks.items()}
        pairs,_=shift.translated_pairs(glyphs,{'a'},distance_limit=10)
        self.assertEqual([(r[0],r[1],r[4]) for r in pairs],[('a','b',3)])

    def test_strict_threshold_boundaries(self):
        a=np.zeros((480,480),bool);a[100:110,100:110]=True
        b=a.copy();b[100,100:105]=False  # Max IoU exactly 95%.
        masks={'a':a,'b':b,'c':np.roll(a,10,axis=0),'d':np.roll(a,9,axis=0)}
        glyphs={c:('font',c,1,int(m.sum()),0,0,'[]','[]',zlib.compress(np.packbits(m).tobytes())) for c,m in masks.items()}
        pairs,_=shift.translated_pairs(glyphs,{'a'},iou_floor=.95,distance_limit=10)
        self.assertEqual([(r[0],r[1]) for r in pairs],[('a','d')])


if __name__=='__main__':unittest.main()
