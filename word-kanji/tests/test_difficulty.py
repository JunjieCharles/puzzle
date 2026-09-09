import unittest
from difficulty import word_counts, clue_score
from scripts.select_one import select_rows
from toy import toy


class DifficultyTests(unittest.TestCase):
    def test_direction_distinct_words_and_only_two_characters(self):
        counts = word_counts([toy(1, 0), toy(1, 2), toy(1, 2), toy(0, 1),
                              toy(3, 0), toy(0, 4), toy(2, 4), toy(0, 5),
                              toy(1), toy(1, 2, 3)])
        row = dict(top=toy(1), left=toy(3), bottom=toy(4), right=toy(5))
        self.assertEqual(clue_score(row, counts), (1, 1, 2, 2))
        self.assertNotEqual(counts[0][toy(1)], counts[1][toy(1)])

    def test_broad_alternatives_raise_score_without_being_hsk_clues(self):
        words = [toy(1, 0), toy(3, 0), toy(0, 4), toy(0, 5)]
        row = dict(top=toy(1), left=toy(3), bottom=toy(4), right=toy(5))
        self.assertEqual(clue_score(row, word_counts(words)), (1, 1, 1, 1))
        self.assertEqual(clue_score(row, word_counts(words + [toy(1, 9), toy(8, 4)])), (1, 1, 2, 2))

    def test_new_difficulty_beats_hsk_grade_then_filters_overlap(self):
        ranks = {ref: 7 if ref <= 4 else 1 for ref in range(1, 8)}
        scores = ({ref: ref for ref in ranks}, {ref: 2 * ref for ref in ranks})
        _, chosen = select_rows([(1, 1, 2, 3, 4), (2, 1, 5, 6, 7), (3, 1, 5, 6, 7)], ranks, scores)
        self.assertEqual([r[0] for r in chosen], [2])
        self.assertEqual(chosen[0][-1], ((1 * 15 + 5) * 15 + 12) * 15 + 14)

    def test_smallest_count_precedes_sum_and_all_ties_are_compared(self):
        scores = ({1: 1, 2: 90, 5: 5, 6: 5}, {3: 90, 4: 90, 7: 5, 8: 5})
        from difficulty import reference_score
        self.assertGreater(reference_score((5, 6, 7, 8), scores), reference_score((1, 2, 3, 4), scores))
        scores[1][8] = 6
        self.assertGreater(reference_score((5, 6, 7, 8), scores), reference_score((5, 6, 7, 7), scores))

    def test_one_per_answer_discards_even_non_overlapping_easier_puzzles(self):
        ranks = {ref: 1 for ref in range(1, 9)}
        scores = ({ref: ref for ref in ranks}, {ref: ref for ref in ranks})
        count, chosen = select_rows([(1, 1, 2, 3, 4), (2, 5, 6, 7, 8), (3, 5, 6, 7, 8)], ranks, scores, limit=1)
        self.assertEqual(count, 3)
        self.assertEqual([row[0] for row in chosen], [2])


if __name__ == "__main__":
    unittest.main()
