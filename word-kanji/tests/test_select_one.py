from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon
from toy import toy
from scripts.enumerate_one import build_database
from scripts.select_one import file_hash, priority, select_database, select_rows


class SelectionTests(unittest.TestCase):
    def test_lowest_grade_is_prioritized_before_highest(self):
        ranks = {1: 1, 2: 7, 3: 7, 4: 7, 5: 5, 6: 5, 7: 5, 8: 5}
        self.assertGreater(priority((5, 6, 7, 8), ranks), priority((1, 2, 3, 4), ranks))

    def test_greedy_conflicts_tie_break_and_no_reuse(self):
        ranks = {i: 7 if i <= 4 else 6 for i in range(1, 13)}
        rows = [(1, 1, 2, 3, 4), (2, 1, 5, 6, 7), (3, 5, 6, 7, 8), (4, 8, 9, 10, 11)]
        count, chosen = select_rows(iter(rows), ranks)
        self.assertEqual(count, 4)
        self.assertEqual([r[0] for r in chosen], [1, 3])
        self.assertEqual(len(set(chosen[0][1:5]) & set(chosen[1][1:5])), 0)

    def test_high_priority_wins_over_source_id(self):
        ranks = {1: 6, 2: 6, 3: 6, 4: 6, 5: 7, 6: 7, 7: 7}
        _, chosen = select_rows([(1, 1, 2, 3, 4), (2, 1, 5, 6, 7)], ranks)
        self.assertEqual([row[0] for row in chosen], [2])

    def test_words_are_reusable_for_different_answers(self):
        records = [{"word": w, "level": "1"} for w in
                   (toy(3), toy(0), toy(8, 3), toy(5, 3), toy(3, 7), toy(3, 0), toy(1, 0), toy(0, 10), toy(0, 2))]
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "all.sqlite", Path(directory) / "selected.sqlite"
            build_database(Lexicon(records, set()), source)
            summary = select_database(source, target, mode="hsk-level")
            self.assertEqual(summary["puzzle_count"], 2)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute("SELECT u.edge_uses FROM word_usage u JOIN words w ON w.id=u.word_id WHERE w.word=?",
                                            (toy(3, 0),)).fetchone()[0], 2)

    def test_dataset_preserves_source_and_grades(self):
        records = [{"word": w, "level": "7-9" if w == toy(0, 10) else "1"}
                   for w in (toy(0), toy(1, 0), toy(3, 0), toy(9, 0), toy(0, 2), toy(0, 4), toy(0, 10))]
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "all.sqlite", Path(directory) / "selected.sqlite"
            build_database(Lexicon(records, set()), source)
            before = file_hash(source)
            summary = select_database(source, target, mode="hsk-level")
            self.assertEqual(summary["puzzle_count"], 1)
            self.assertEqual(summary["counts_by_max_hsk_level"], {"7-9": 1})
            self.assertEqual(summary["canonical_candidates"], 9)
            self.assertEqual(summary["discarded_for_word_overlap"], 35)
            self.assertEqual(before, file_hash(source))
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute("SELECT SUM(edge_uses) FROM word_usage").fetchone()[0], 4)
                row = db.execute("SELECT answer,max_level,bottom_word,right_word FROM puzzle_details").fetchone()
                self.assertEqual(row[:2], (toy(0), "7-9"))
                self.assertIn(toy(0, 10), row[2:])
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(FileExistsError):
                select_database(source, source)
            with self.assertRaises(FileExistsError):
                select_database(source, target)
            low = select_database(source, Path(directory) / "low.sqlite", "6")
            self.assertEqual(low["counts_by_max_hsk_level"], {"1": 1})


if __name__ == "__main__":
    unittest.main()
