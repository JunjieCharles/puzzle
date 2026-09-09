from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator import Lexicon, Puzzle, generate, level_rank, make_record, solve
from toy import toy
from scripts.import_lexicons import normalize_headword


def synthetic_lexicon(words, extra=()):
    # Synthetic sets exercise constraints; they make no claim about real Chinese.
    return Lexicon([{"word": w, "level": "1"} for w in words], set(extra))


class SolverTests(unittest.TestCase):
    def setUp(self):
        self.one = Puzzle((toy(1),), (toy(2),), toy(3), toy(4))
        self.common = {toy(0), toy(1, 0), toy(0, 2), toy(3, 0), toy(0, 4)}

    def test_one_character_unique(self):
        self.assertEqual(solve(self.one, synthetic_lexicon(self.common)), [toy(0)])
        self.assertTrue(self.one.distinct(toy(0)))

    def test_missing_whole_answer_rejected(self):
        self.assertEqual(solve(self.one, synthetic_lexicon(self.common - {toy(0)})), [])

    def test_word_order_matters(self):
        words = (self.common - {toy(1, 0)}) | {toy(0, 1)}
        self.assertEqual(solve(self.one, synthetic_lexicon(words)), [])

    def test_rare_repeated_alternative_not_filtered(self):
        # A synthetic alternative repeats a clue but must still invalidate uniqueness.
        extra = {toy(3), toy(1, 3), toy(3, 2), toy(3, 3), toy(3, 4)}
        lexicon = synthetic_lexicon(self.common, extra)
        self.assertEqual(set(solve(self.one, lexicon)), {toy(0), toy(3)})
        self.assertFalse(self.one.distinct(toy(3)))

    def test_hsk_seven_nine_alternative_audited_at_level_six(self):
        extra = {toy(3), toy(1, 3), toy(3, 2), toy(3, 3), toy(3, 4)}
        records = [{"word": w, "level": "1"} for w in self.common]
        records += [{"word": w, "level": "7-9"} for w in extra]
        lexicon = Lexicon(records, set())
        self.assertNotIn(toy(1, 3), lexicon.words_up_to("6"))
        self.assertIn(toy(1, 3), lexicon.words_up_to("7-9"))
        self.assertEqual(set(solve(self.one, lexicon)), {toy(0), toy(3)})

    def test_two_character_chain(self):
        puzzle = Puzzle((toy(5), toy(6)), (toy(7), toy(2)), toy(8), toy(4))
        words = {toy(3, 0), toy(8, 3), toy(5, 3), toy(3, 7), toy(6, 0), toy(0, 2), toy(0, 4)}
        self.assertEqual(solve(puzzle, synthetic_lexicon(words)), [toy(3, 0)])
        self.assertEqual(len(puzzle.edge_words(toy(3, 0))), 7)
        self.assertTrue(puzzle.distinct(toy(3, 0)))
        self.assertEqual(solve(puzzle, synthetic_lexicon(words - {toy(3, 0)})), [])

    def test_fixed_fixed_and_answer_answer_repetition(self):
        self.assertFalse(Puzzle((toy(1),), (toy(2),), toy(1), toy(4)).distinct(toy(0)))
        self.assertFalse(Puzzle((toy(5), toy(6)), (toy(7), toy(2)), toy(8), toy(4)).distinct(toy(3, 3)))

    def test_invalid_layout(self):
        with self.assertRaises(ValueError):
            Puzzle((toy(5), toy(6)), (toy(2),), toy(8), toy(4))
        with self.assertRaises(ValueError):
            Puzzle((toy(1, 12),), (toy(2),), toy(3), toy(4))


class ImportTests(unittest.TestCase):
    def test_sense_numbers_and_optional_hanzi(self):
        self.assertEqual(normalize_headword("本1"), ["本"])
        self.assertEqual(set(normalize_headword("没（有）")), {"没", "没有"})
        self.assertEqual(set(normalize_headword("有（一）点儿")), {"有点儿", "有一点儿"})
        self.assertEqual(normalize_headword("ABC"), [])
        self.assertEqual(normalize_headword("面条儿"), ["面条儿"])


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lexicon = Lexicon.load()

    def test_2025_snapshot_and_annotation(self):
        self.assertEqual(self.lexicon.metadata["hsk_numbered_entries"], 11000)
        self.assertEqual(len(self.lexicon.records), 10902)
        self.assertEqual({r["level"] for r in self.lexicon.records.values()}, {"1", "2", "3", "4", "5", "6", "7-9"})
        self.assertTrue(any(len(r["levels"]) > 1 for r in self.lexicon.records.values()))
        self.assertGreater(len(self.lexicon.broad_answers[2]), 50000)

    def test_seed_reproducibility_and_ceiling(self):
        first = generate(self.lexicon, 2, 3, "6", random.Random(123))
        self.assertEqual(first, generate(self.lexicon, 2, 3, "6", random.Random(123)))
        self.assertNotEqual(first, generate(self.lexicon, 2, 3, "6", random.Random(124)))
        for puzzle, answer in first:
            self.assertTrue(puzzle.distinct(answer))
            self.assertEqual(solve(puzzle, self.lexicon), [answer])
            for word in [answer] + [w for _, w in puzzle.edge_words(answer)]:
                self.assertLessEqual(level_rank(self.lexicon.records[word]["level"]), 6)

    def test_seven_nine_generation_supported(self):
        results = generate(self.lexicon, 1, 2, "7-9", random.Random(5))
        self.assertEqual(len(results), 2)
        for puzzle, answer in results:
            self.assertEqual(solve(puzzle, self.lexicon), [answer])

    def test_impossible_request_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "Only found"):
            generate(synthetic_lexicon({toy(3)}), 1, 1, "6", random.Random(0))

    def test_example_batch_independently(self):
        rng = random.Random(93427)
        batch = {"puzzles": [make_record(p, a, self.lexicon, i + 1)
                             for size in (1, 2)
                             for i, (p, a) in enumerate(generate(self.lexicon, size, 5, "6", rng))]}
        self.assertEqual([p["size"] for p in batch["puzzles"]].count(1), 5)
        self.assertEqual([p["size"] for p in batch["puzzles"]].count(2), 5)
        for item in batch["puzzles"]:
            layout = item["layout"]
            puzzle = Puzzle(tuple(layout["top"]), tuple(layout["bottom"]), layout["left"], layout["right"])
            answer = item["answer"]["word"]
            self.assertEqual(solve(puzzle, self.lexicon), [answer])
            self.assertTrue(puzzle.distinct(answer))
            self.assertEqual(item["grid"], puzzle.grid())
            self.assertTrue(all(e["hsk_level"] == self.lexicon.records[e["word"]]["level"] for e in item["edge_words"]))
            self.assertTrue(all(level_rank(e["hsk_level"]) <= 6 for e in item["edge_words"]))
            # Independently reconstruct every arrow from the rendered grid.
            grid = item["grid"]
            rendered_words = []
            def value(row, col):
                cell = grid[row][col]
                return answer["①②".index(cell)] if cell in ("①", "②") else cell
            for row, cells in enumerate(grid):
                for col, cell in enumerate(cells):
                    if cell == "→":
                        rendered_words.append(value(row, col - 1) + value(row, col + 1))
                    elif cell == "↓":
                        rendered_words.append(value(row - 1, col) + value(row + 1, col))
            self.assertCountEqual(rendered_words, [e["word"] for e in item["edge_words"]])


if __name__ == "__main__":
    unittest.main()
