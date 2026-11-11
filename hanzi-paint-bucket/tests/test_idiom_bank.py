import importlib.util
from pathlib import Path
import random
import unittest

spec=importlib.util.spec_from_file_location('idiom',Path(__file__).resolve().parents[1]/'scripts/build_idiom_bank.py')
idiom=importlib.util.module_from_spec(spec);spec.loader.exec_module(idiom)


class IdiomTests(unittest.TestCase):
    def test_zero_to_two_rectangles_do_not_require_alignment(self):
        import numpy as np
        mask=np.zeros((160,160),dtype=bool)
        self.assertTrue(idiom.has_zero_to_two_rectangular_regions(mask))
        mask[2,2]=True
        self.assertFalse(idiom.has_zero_to_two_rectangular_regions(mask))
        mask[10:35,20:50]=True
        self.assertTrue(idiom.has_zero_to_two_rectangular_regions(mask))
        mask[110:140,100:145]=True
        self.assertTrue(idiom.has_zero_to_two_rectangular_regions(mask))
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))
        mask[70:75,70:75]=True
        self.assertFalse(idiom.has_zero_to_two_rectangular_regions(mask))
        mask[70:75,70:75]=False;mask[20:25,30:35]=False
        self.assertFalse(idiom.has_zero_to_two_rectangular_regions(mask))

    def test_few_rectangles_filter_requires_every_position(self):
        areas={'a':100,'b':200,'x':0,'c':150}
        simple={'a','b','x'}
        for word in ['ab','axb','axbx']:
            self.assertTrue(idiom.word_pattern_excluded(word,areas,set(),(),simple))
        for word in ['ac','abc','acbx']:
            self.assertFalse(idiom.word_pattern_excluded(word,areas,set(),(),simple))

    def test_all_painted_grid_positions_excluded_across_word_lengths(self):
        areas={'a':100,'b':200,'c':150,'d':160,'x':0,'y':0,'t':1}
        grid={'a','b','c','d'}
        for word in ['ab','axb','axby','xaby','abc','abcx','abcd']:
            self.assertTrue(idiom.word_pattern_excluded(word,areas,set(),grid))
        for word in ['abct','abtx','axxy','xxxx']:
            self.assertFalse(idiom.all_painted_glyphs_are_grids(word,areas,grid))
        self.assertFalse(idiom.word_pattern_excluded('abtx',areas,set(),grid))
        self.assertTrue(idiom.word_pattern_excluded('xyab',areas,set(),set()))

    def test_matrix_allows_minor_edge_slope_but_not_interior_holes(self):
        import numpy as np
        mask=np.zeros((160,260),dtype=bool)
        mask[20:120,10:110]=True;mask[20:120,122:222]=True
        mask[20:100,221]=False
        self.assertTrue(idiom.is_regular_rectangle_grid(mask))
        self.assertFalse(idiom.bank.is_single_solid_rectangle(mask[:,120:]))
        mask[60,160]=False
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))

    def test_rectangle_grid_requires_full_aligned_cells(self):
        import numpy as np
        mask=np.zeros((100,100),dtype=bool)
        for y in (10,40):
            for x in (10,45):mask[y:y+20,x:x+25]=True
        self.assertTrue(idiom.is_regular_rectangle_grid(mask))
        mask[90,90]=True
        self.assertTrue(idiom.is_regular_rectangle_grid(mask))
        mask[40:60,45:70]=False
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))
        mask[40:60,50:75]=True
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))
        mask[40:60,50:75]=False;mask[40:60,45:70]=True
        mask[15:20,15:20]=False
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))
        self.assertFalse(idiom.is_regular_rectangle_grid(np.zeros((100,100),dtype=bool)))

    def test_rectangle_grid_allows_single_column_and_filters_grid_only_words(self):
        import numpy as np
        mask=np.zeros((120,120),dtype=bool)
        for y in (10,40,70):mask[y:y+20,10:40]=True
        self.assertTrue(idiom.is_regular_rectangle_grid(mask))
        self.assertTrue(idiom.is_regular_rectangle_grid(mask.T))
        areas=dict.fromkeys('abc',100)
        self.assertTrue(idiom.word_pattern_excluded('ab',areas,set(),{'a','b'}))
        self.assertFalse(idiom.word_pattern_excluded('ac',areas,set(),{'a','b'}))
        self.assertTrue(idiom.word_pattern_excluded('abc',areas,set(),{'a','b','c'}))

    def test_four_separated_corner_blocks_are_not_a_compact_grid(self):
        import numpy as np
        mask=np.zeros((160,160),dtype=bool)
        for y in (10,110):
            for x in (10,110):mask[y:y+25,x:x+25]=True
        self.assertFalse(idiom.is_regular_rectangle_grid(mask))

    def test_mean_paint_area_orders_mixed_lengths_and_counts_blanks(self):
        from fractions import Fraction
        areas={'a':100,'b':40,'c':10,'x':0}
        scores=idiom.bank.arithmetic_scores(['ab','abc','abxx'],areas)
        self.assertEqual(scores,{'ab':Fraction(70),'abc':Fraction(50),'abxx':Fraction(35)})
        selected,_=idiom.select_disjoint(list(scores),scores,scope_by_length={2:2,3:2,4:4})
        self.assertEqual(selected,['abc','abxx'])

    def test_word_pattern_filter_preserves_individual_characters(self):
        areas={'a':100,'b':100,'x':0,'y':0,'t':1}
        day={'a','b'}
        self.assertTrue(idiom.word_pattern_excluded('ab',areas,day))
        self.assertFalse(idiom.word_pattern_excluded('at',areas,day))
        self.assertFalse(idiom.word_pattern_excluded('abt',areas,day))
        self.assertTrue(idiom.word_pattern_excluded('xyab',areas,day))
        self.assertTrue(idiom.word_pattern_excluded('abxy',areas,day))
        self.assertFalse(idiom.word_pattern_excluded('axby',areas,day))
        self.assertFalse(idiom.word_pattern_excluded('xtab',areas,day))

    def test_day_shape_two_aligned_boxes_and_noise(self):
        import numpy as np
        mask=np.zeros((100,100),dtype=bool)
        mask[10:35,20:50]=True;mask[40:65,20:50]=True
        self.assertTrue(idiom.is_day_shaped(mask))
        mask[90,90]=True
        self.assertTrue(idiom.is_day_shaped(mask))
        mask[75:80,20:25]=True
        self.assertFalse(idiom.is_day_shaped(mask))
        mask[75:80,20:25]=False;mask[40:65,20:50]=False;mask[40:65,35:65]=True
        self.assertFalse(idiom.is_day_shaped(mask))

    def test_shared_two_three_pool_and_separate_four_pool(self):
        scores={'ab':.2,'acd':.1,'aefg':.5,'hij':.4}
        selected,_=idiom.select_disjoint(list(scores),scores,scope_by_length={2:2,3:2,4:4})
        self.assertEqual(selected,['aefg','hij','acd'])
        scores['ab']=.05
        selected,_=idiom.select_disjoint(list(scores),scores,scope_by_length={2:2,3:2,4:4})
        self.assertEqual(selected,['aefg','hij','ab'])

    def test_three_character_words_require_no_blank(self):
        glyphs={c:('font',c,1,area) for c,area in {'a':50,'b':60,'r':100,'x':0}.items()}
        rect={'r'}
        self.assertTrue(idiom.combined_eligible('ab',glyphs,rect))
        self.assertTrue(idiom.combined_eligible('abr',glyphs,rect))
        self.assertFalse(idiom.combined_eligible('abx',glyphs,rect))
        self.assertTrue(idiom.combined_eligible('abrx',glyphs,rect))
        self.assertFalse(idiom.combined_eligible('arx',glyphs,rect))

    def test_combined_reuse_per_length_and_mixed_score_order(self):
        scores={'ab':.2,'ac':.8,'adef':.6,'ghij':.1}
        selected,used=idiom.select_disjoint(list(scores),scores,per_length=True)
        self.assertEqual(selected,['adef','ab','ghij'])
        self.assertEqual(used,set('abdefghij'))
        self.assertEqual(idiom.select_disjoint(list(scores),scores,per_length=False)[0],['ab','ghij'])

    def test_two_informative_characters_allow_other_rectangles_or_blanks(self):
        glyphs={c:('font',c,1,area) for c,area in {'a':50,'b':60,'r':100,'x':0}.items()}
        rectangles={'r'}
        self.assertEqual(idiom.informative_count('ab',glyphs,rectangles),2)
        self.assertEqual(idiom.informative_count('abrx',glyphs,rectangles),2)
        self.assertEqual(idiom.informative_count('arxx',glyphs,rectangles),1)
        self.assertEqual(idiom.informative_count('rx',glyphs,rectangles),0)
        self.assertEqual(glyphs['r'][3],100)

    def test_mixed_word_lengths_are_not_alternatives(self):
        areas={'a':100,'b':100,'x':0,'y':0}
        words=['abx','abxy','abyx']
        _,matches=idiom.alternative_matches(words,words,areas,[])
        self.assertEqual(len(matches['abx']),1)
        self.assertEqual(len(matches['abxy']),2)

    def test_three_and_four_character_candidate_rule(self):
        def row(c,area):return ('font',c,1 if area else 0,area,0,0,f'[{area}]' if area else '[]','[]',b'')
        glyphs={c:row(c,a) for c,a in {'a':25,'b':40,'x':0,'y':0}.items()}
        selected,_=idiom.idiom_candidates(['abx','abxy','axy'],glyphs,set())
        self.assertEqual(selected,['abx','abxy'])

    def test_blank_glyphs_match_other_blank_characters(self):
        areas={'a':100,'b':100,'x':0,'y':0,'z':0,'t':1}
        words=['abxy','abzz','abxt']
        _,matches=idiom.alternative_matches(words,['abxy'],areas,[])
        self.assertEqual(len(matches['abxy']),2)

    def test_no_transitive_shape_similarity(self):
        areas=dict.fromkeys('abcdefxy',100);areas['x']=areas['y']=0
        words=['adxy','cdxy']
        _,matches=idiom.alternative_matches(words,['adxy'],areas,[('a','b'),('b','c')])
        self.assertEqual(len(matches['adxy']),1)

    def test_shape_rejected_or_repeated_competitor_still_counts(self):
        areas=dict.fromkeys('abcd',100);areas['x']=areas['y']=0
        _,matches=idiom.alternative_matches(['abxy','aaxy'],['abxy'],areas,[('a','b')])
        self.assertEqual(len(matches['abxy']),2)

    def test_two_visible_minimum_and_noise_not_erased(self):
        def row(c,area):return ('font',c,1 if area else 0,area,0,0,f'[{area}]' if area else '[]','[]',b'')
        glyphs={c:row(c,a) for c,a in {'a':25,'b':40,'x':0,'y':0,'t':24}.items()}
        candidates,stats=idiom.idiom_candidates(['abxy','axyy','abtx'],glyphs,set())
        self.assertEqual(candidates,['abxy'])
        self.assertEqual(stats['at_least_two_painted'],2)
        self.assertEqual(stats['excluded_tiny_region_words'],1)
        self.assertEqual(idiom.idiom_candidates(['abxy'],glyphs,{'a'})[0],[])

    def test_index_matches_brute_force(self):
        rng=random.Random(31);chars='abcdef'
        areas={'a':0,'b':0,'c':30,'d':40,'e':50,'f':60}
        pairs=[('c','d'),('d','e')];adj={frozenset(p) for p in pairs}
        words=sorted({''.join(rng.choices(chars,k=4)) for _ in range(100)})
        order,matches=idiom.alternative_matches(words,words,areas,pairs)
        for w in words:
            expected=[i for i,v in enumerate(order) if all((areas[a]==areas[b]==0) or (areas[a]>0 and areas[b]>0 and (a==b or frozenset((a,b)) in adj)) for a,b in zip(w,v))]
            self.assertEqual(matches[w],expected)

    def test_private_output_boundary(self):
        with self.assertRaises(ValueError):idiom.private_path(idiom.REPO/'ignored-output')


if __name__=='__main__':unittest.main()
