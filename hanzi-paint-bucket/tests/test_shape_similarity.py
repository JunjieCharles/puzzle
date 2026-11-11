"""Synthetic arbitrary-mask geometry and conservative-pruning checks."""
import sys
from pathlib import Path
import unittest

import numpy as np
from scipy import ndimage

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_shape_similarity import normalized_iou, overlap_axis, shape_signature, find_pairs


class ShapeSimilarityTests(unittest.TestCase):
    def test_nonrectangle_stretch_and_holes(self):
        a=np.ones((8,8),dtype=bool);a[2:6,2:6]=False
        b=np.repeat(np.repeat(a,3,axis=0),2,axis=1)
        self.assertAlmostEqual(normalized_iou(a,b),1)
        self.assertAlmostEqual(normalized_iou(a,np.ones((5,7),dtype=bool)),.75)

    def test_independent_integer_grid_oracle(self):
        rng=np.random.default_rng(47)
        for _ in range(15):
            a=rng.random((3,4))>.4;b=rng.random((5,7))>.4
            aa=np.repeat(np.repeat(a,5,axis=0),7,axis=1)
            bb=np.repeat(np.repeat(b,3,axis=0),4,axis=1)
            exact=(aa&bb).sum()/(aa|bb).sum()
            self.assertAlmostEqual(normalized_iou(a,b),exact)

    def test_axis_partition_conservation(self):
        for n,m in [(3,7),(17,8),(1,19)]:
            weights=overlap_axis(n,m)
            np.testing.assert_allclose(np.asarray(weights.sum(axis=1)).ravel(),1/n)
            np.testing.assert_allclose(np.asarray(weights.sum(axis=0)).ravel(),1/m)

    def test_noise_not_converted_to_blank(self):
        mask=np.zeros((40,40),dtype=bool);mask[0:4,0:6]=True
        self.assertIsNone(shape_signature(mask))
        mask[20:25,20:25]=True
        crop,center=shape_signature(mask)
        self.assertEqual(crop.shape,(5,5))
        np.testing.assert_array_equal(center,[22.5,22.5])

    def test_pruning_matches_all_pairs_and_boundary(self):
        rng=np.random.default_rng(12)
        shapes={str(i):(rng.random((3+i%3,4+i%2))>.3,np.array([float(i),0])) for i in range(12)}
        threshold=.4;limit=5
        actual,_=find_pairs(shapes,set(shapes),threshold,limit)
        expected=set()
        for a in shapes:
            for b in shapes:
                if a<b and ndimage.label(shapes[a][0])[1]==ndimage.label(shapes[b][0])[1] and np.abs(shapes[a][1]-shapes[b][1]).sum()<=limit and normalized_iou(shapes[a][0],shapes[b][0])>threshold:
                    expected.add((a,b))
        self.assertEqual({(a,b) for a,b,*_ in actual},expected)
        full=np.ones((10,10),dtype=bool)
        reduced=full.copy();reduced[0]=False
        pairs,_=find_pairs({'a':(full,np.array([0,0])),'b':(reduced,np.array([50,0]))},{'a'},.9,50)
        self.assertEqual(pairs,[])
        pairs,_=find_pairs({'a':(full,np.array([0,0])),'b':(full,np.array([50,0]))},{'a'},.9,50)
        self.assertEqual(len(pairs),1)

    def test_component_count_rejects_high_iou(self):
        a=np.ones((40,40),dtype=bool)
        b=a.copy();b[:,20]=False
        self.assertGreater(normalized_iou(a,b),.9)
        pairs,_=find_pairs({'a':(a,np.array([0,0])),'b':(b,np.array([0,0]))},{'a'},.9,50)
        self.assertEqual(pairs,[])


if __name__=='__main__':unittest.main()
