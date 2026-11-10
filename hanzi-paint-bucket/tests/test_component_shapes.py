import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('component_shapes',Path(__file__).resolve().parents[1]/'scripts/component_shapes.py')
shapes=importlib.util.module_from_spec(spec);spec.loader.exec_module(shapes)


class ComponentShapeTests(unittest.TestCase):
    def test_recursive_membership_cycles_and_extra_regions(self):
        graph={'a':{'b'},'b':{'a','月'},'c':{'开'},'d':{'a'},'e':{'c'},'f':{'开'}}
        areas={'a':[100,80,24],'b':[100,80,25],'c':[100,1],
               'd':[100],'e':[100,25],'f':[24]}
        moon,kai=shapes.structural_paint_classes(areas,areas,graph)
        self.assertEqual(moon,{'a'})
        self.assertEqual(kai,{'c'})
        self.assertFalse(shapes.contains_component('a','开',graph))
        self.assertEqual(areas['a'],[100,80,24])

    def test_self_component_matches(self):
        self.assertTrue(shapes.contains_component('月','月',{'月':{'月'}}))


if __name__=='__main__':unittest.main()
