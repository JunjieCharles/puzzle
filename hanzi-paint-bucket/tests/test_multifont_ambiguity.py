"""Synthetic words verify production ambiguity composition, without real answers."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from multifont_ambiguity import match_font


class MultifontAmbiguityTests(unittest.TestCase):
    def test_no_cross_font_position_mixing(self):
        words=['ab','cd'];areas=dict.fromkeys('abcd',100);counts=dict.fromkeys('abcd',2)
        first=match_font(words,['ab'],areas,[],[('a','c',.99,1)],counts)
        second=match_font(words,['ab'],areas,[],[('b','d',.99,1)],counts)
        self.assertEqual(first['ab']|second['ab'],{'ab'})
        complete=match_font(words,['ab'],areas,[('a','c',99,100,1,0,1)],[('b','d',.99,1)],counts)
        self.assertEqual(complete['ab'],{'ab','cd'})

    def test_pixel_pairs_cannot_bypass_component_count(self):
        areas=dict.fromkeys('abcd',100);counts={'a':2,'b':2,'c':3,'d':2}
        result=match_font(['ab','cd'],['ab'],areas,[('a','c',99,100,1,0,1)],[('b','d',.99,1)],counts)
        self.assertEqual(result['ab'],{'ab'})
        result=match_font(['ab','cd'],['ab'],areas,[],[('a','c',.99,1),('b','d',.99,1)],counts)
        self.assertEqual(result['ab'],{'ab'})

    def test_excluded_target_words_remain_competitors_and_blanks_match(self):
        result=match_font(['ab','cd'],['ab'],{'a':100,'c':100,'b':0,'d':0},[],[('a','c',.99,1)],{'a':2,'c':2,'b':0,'d':0})
        self.assertEqual(result['ab'],{'ab','cd'})


if __name__=='__main__':unittest.main()
