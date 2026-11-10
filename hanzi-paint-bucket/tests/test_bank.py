import importlib.util
from pathlib import Path
import unittest
import zlib
import numpy as np

spec=importlib.util.spec_from_file_location('bank',Path(__file__).resolve().parents[1]/'scripts/build_hsk_bank.py')
bank=importlib.util.module_from_spec(spec);spec.loader.exec_module(bank)


class BankTests(unittest.TestCase):
    def test_arithmetic_average_preserves_zero_partner_information(self):
        from fractions import Fraction as F
        scores=bank.arithmetic_scores(['za','zb','ab','cc'],{'z':F(0),'a':F(4,5),'b':F(1,5),'c':F(1,2)})
        self.assertEqual(scores['za'],F(2,5))
        self.assertEqual(scores['zb'],F(1,10))
        self.assertEqual(scores['ab'],scores['cc'])
        self.assertEqual(scores['ab'],F(1,2))

    def test_length_filter_precedes_character_conflicts(self):
        selected,_=bank.select_words(['abc','ad','be'],dict.fromkeys('abcde',1),
            scores={'abc':0,'ad':1,'be':2},word_length=2)
        self.assertEqual(selected,['be','ad'])

    def test_geometric_score_considers_every_character_and_word_length(self):
        from fractions import Fraction as F
        ratios={'a':F(8,10),'b':F(1,10),'c':F(7,10),'d':F(1,2),'e':F(1,2),'f':F(1,2),'z':F(0)}
        scores,power=bank.geometric_scores(['ab','ac','de','def','az'],ratios)
        self.assertEqual(power,6)
        self.assertLess(scores['ab'],scores['ac'])
        self.assertEqual(scores['de'],scores['def'])
        self.assertEqual(scores['az'],0)
        self.assertAlmostEqual(float(scores['ab'])**(1/power),.08**.5)

    def test_minimum_area_is_per_component_not_sum(self):
        selected,stats=bank.select_words(['ab','cd','ef'],dict.fromkeys('abcdef',30),
            component_areas={'a':[15,15],'b':[30],'c':[25,1],'d':[25],'e':[24],'f':[30]})
        self.assertEqual(selected,['cd'])
        self.assertEqual(stats['excluded_tiny_region_words'],2)
        self.assertEqual(stats['after_minimum_region_filter'],1)

    def test_function_words_mixed_senses_and_private_overrides(self):
        entries=[{'word':'ab','entries':[{'part_of_speech':'副、连'}]},
                 {'word':'cd','entries':[{'part_of_speech':'副、动'}]},
                 {'word':'ef','entries':[]}]
        excluded=bank.policy_module.editorial_exclusions(entries,{'excluded_words':[{'word':'ef','reason':'manual'}]})
        self.assertEqual(set(excluded),{'ef'})
        self.assertEqual(bank.policy_module.editorial_exclusions(entries,{'excluded_words':[]}),{})

    def test_structural_ban_only_two_characters_and_one_nonnoise_region(self):
        policy={'two_character_single_component_characters':['a','b','c','d']}
        areas={'a':[25,1,24],'b':[25,25],'c':[24],'d':[100]}
        words=['ax','xa','bx','cx','dx','axy','dxyz']
        excluded,characters=bank.policy_module.two_character_component_exclusions(words,policy,areas)
        self.assertEqual(characters,{'a','d'})
        self.assertEqual(excluded,{'ax','xa','dx'})
        self.assertEqual(areas['a'],[25,1,24])

    def test_positional_ban_across_lengths_without_banning_character(self):
        policy={'excluded_words':[], 'excluded_character_positions':[
            {'character':'a','position':2,'reason':'manual'}]}
        words=['a','ab','ba','bac','bacd','bca']
        result=bank.policy_module.editorial_exclusions([{'word':w} for w in words],policy)
        self.assertEqual(set(result),{'ba','bac','bacd'})
        policy['excluded_character_positions'][0]['position']=0
        with self.assertRaises(ValueError):bank.policy_module.editorial_exclusions([],policy)

    def test_editorial_filter_precedes_global_selection_but_not_ambiguity(self):
        policy={'excluded_words':[{'word':'cd','reason':'manual'}],
                'excluded_characters':[{'character':'a','reason':'manual'}]}
        excluded=bank.policy_module.editorial_exclusions([{'word':w} for w in ['ab','ba','cd','ef']],policy)
        self.assertEqual(set(excluded),{'ab','ba','cd'})
        selected,summary=bank.select_words(['ab','ac'],dict.fromkeys('abc',1),excluded_words={'ab'})
        self.assertEqual(selected,['ac'])
        self.assertEqual(summary['excluded_editorial_words'],1)
        ambiguous=bank.ambiguous_words(['ab','cb'],[('a','c')],['ab'])
        self.assertEqual(bank.select_words(['ab','cb'],dict.fromkeys('abc',1),ambiguous,excluded_words={'cb'})[0],[])
    def test_stroke_ratio_controls_conflict_selection_and_display_order(self):
        areas={'a':100,'b':100,'c':1,'d':1,'e':1}
        words,_=bank.select_words(['ab','ac','de'],areas,scores={'ab':.2,'ac':.8,'de':.5})
        self.assertEqual(words,['de','ab'])

    def test_single_rectangle_excludes_only_complete_solid_rectangle(self):
        mask=np.zeros((120,120),dtype=bool);mask[10:110,10:110]=True
        self.assertTrue(bank.is_single_solid_rectangle(mask))
        self.assertFalse(bank.is_single_solid_rectangle(np.zeros_like(mask)))
        corner=mask.copy();corner[10,10]=False
        self.assertTrue(bank.is_single_solid_rectangle(corner))
        for position in [(12,50),(50,50)]:
            altered=mask.copy();altered[position]=False
            self.assertFalse(bank.is_single_solid_rectangle(altered))
        altered=mask.copy();altered[50,:]=False
        self.assertFalse(bank.is_single_solid_rectangle(altered))
        altered=mask.copy();altered[118,118]=True
        self.assertTrue(bank.is_single_solid_rectangle(altered))

    def test_rectangle_noise_threshold_and_original_mask_preserved(self):
        mask=np.zeros((100,100),dtype=bool);mask[10:50,10:50]=True
        mask[70:74,70:76]=True  # 24 pixels: ignored by classification.
        original=mask.copy()
        self.assertTrue(bank.is_single_solid_rectangle(mask))
        np.testing.assert_array_equal(mask,original)
        mask[74,70]=True  # 25 pixels: a second real region must remain.
        self.assertFalse(bank.is_single_solid_rectangle(mask))
        self.assertFalse(bank.is_single_solid_rectangle(original & ~ (np.indices(mask.shape)[0]<60)))

    def test_bbox_filter_preserves_holes_and_inward_slits(self):
        mask=np.ones((200,200),dtype=bool)
        edge=mask.copy();edge[0,40:90]=False
        self.assertTrue(bank.is_single_solid_rectangle(edge))
        hole=mask.copy();hole[1,50]=False
        self.assertFalse(bank.is_single_solid_rectangle(hole))
        slit=mask.copy();slit[:12,100]=False
        self.assertGreater(slit.mean(),.995)
        self.assertFalse(bank.is_single_solid_rectangle(slit))
        notch=mask.copy();notch[:10,:30]=False
        self.assertFalse(bank.is_single_solid_rectangle(notch))

    def test_rectangle_words_removed_before_global_selection_only(self):
        competitors=['ab','cb','de']
        ambiguous=bank.ambiguous_words(competitors,[('a','c')],['ab','de'])
        selected,stats=bank.select_words(competitors,dict.fromkeys('abcde',1),ambiguous,{'c'})
        self.assertEqual(selected,['de'])
        self.assertEqual(stats['excluded_single_rectangle_words'],1)

    def test_hardest_conflict_wins_and_display_order_is_reversed(self):
        areas={'a':1,'b':2,'c':20,'d':5,'e':6}
        words,stats=bank.select_words(['ab','ac','de','aa','a','bz'],areas)
        self.assertEqual(words,['de','ab'])
        self.assertEqual(stats['all_characters_paintable'],4)
        self.assertEqual(stats['excluded_internal_repetition'],1)
        self.assertEqual(stats['excluded_global_conflicts'],1)

    def test_ties_are_deterministic_and_three_letter_words_work(self):
        areas=dict.fromkeys('abcdef',1)
        self.assertEqual(bank.select_words(['bc','ab','def'],areas)[0],['def','ab'])
        self.assertEqual(bank.select_words(['def','ab','bc','ab'],areas)[0],['def','ab'])

    def test_nonpositive_and_empty_cases(self):
        self.assertEqual(bank.select_words(['ab','cd'],{'a':1,'b':0,'c':-1,'d':1})[0],[])

    def test_ambiguous_character_can_form_unique_word(self):
        self.assertEqual(bank.ambiguous_words(['ab','cd'],[('a','c')]),set())
        self.assertEqual(bank.ambiguous_words(['ab','cb','de'],[('a','c')]),{'ab','cb'})

    def test_repeated_words_still_compete_as_alternatives(self):
        ambiguous=bank.ambiguous_words(['aa','ab','cd'],[('a','b')])
        self.assertEqual(ambiguous,{'aa','ab'})
        words,stats=bank.select_words(['aa','ab','cd'],dict.fromkeys('abcd',1),ambiguous)
        self.assertEqual(words,['cd'])
        self.assertEqual(stats['excluded_ambiguous_words'],2)

    def test_extended_word_outside_target_set_can_disqualify_hsk_word(self):
        self.assertEqual(bank.ambiguous_words(['ab','cb','de'],[('a','c')],['ab','de']),{'ab'})
        self.assertEqual(bank.ambiguous_words(['ab','cd'],[('a','c')],['ab']),set())

    def test_query_shape_pairs_match_brute_force(self):
        base=np.zeros((480,480),dtype=np.uint8);base[180:260,170:270]=1
        masks={'a':base,'b':np.roll(base,1,axis=0),'c':np.roll(base,80,axis=0),'d':base.copy()}
        glyphs={c:('font',c,1,int(m.sum()),0,0,'[]','[]',zlib.compress(np.packbits(m).tobytes())) for c,m in masks.items()}
        actual={frozenset((a,b)):d for a,b,d in bank.query_shape_pairs(glyphs,{'b','c'},.05)}
        expected={}
        for a in ['b','c']:
            for b in masks:
                if a==b: continue
                distance=np.logical_xor(masks[a],masks[b]).sum()/np.logical_or(masks[a],masks[b]).sum()
                if distance<=.05: expected[frozenset((a,b))]=distance
        self.assertEqual(actual,expected)


if __name__ == '__main__':
    unittest.main()
