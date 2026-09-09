import itertools
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon, Puzzle, solve
from toy import toy
from scripts.enumerate_one import build_database, canonical_candidates, orientations


class EnumerateOneTests(unittest.TestCase):
    def lexicon(self, extra=()):
        words = {toy(0), toy(1, 0), toy(3, 0), toy(9, 0), toy(0, 2), toy(0, 4), toy(0, 10)}
        return Lexicon([{"word": w, "level": "7-9" if w == toy(0, 10) else "1"} for w in words], set(extra))

    def test_exhaustive_against_cartesian_product_and_original_solver(self):
        lexicon = self.lexicon()
        expected = set()
        for top, left, bottom, right in itertools.product(toy(1, 3, 9), toy(1, 3, 9), toy(2, 4, 10), toy(2, 4, 10)):
            p = Puzzle((top,), (bottom,), left, right)
            if p.distinct(toy(0)) and solve(p, lexicon) == [toy(0)]:
                expected.add((top, left, bottom, right))
        actual = {c for _, t, l, b, r, unique in canonical_candidates(lexicon) if unique
                  for c in orientations(t, l, b, r)}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 36)

    def test_repeated_letter_alternative_rejects_entire_four_orientation_group(self):
        lexicon = self.lexicon({toy(3), toy(1, 3), toy(3, 3), toy(9, 3), toy(3, 2), toy(3, 4), toy(3, 10)})
        candidates = list(canonical_candidates(lexicon))
        self.assertEqual(len(candidates), 9)
        self.assertTrue(all(not row[-1] for row in candidates))

    def test_level_ceiling_and_database_view_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "puzzles.sqlite"
            summary = build_database(self.lexicon(), path)
            self.assertEqual(summary["candidate_count"], 36)
            self.assertEqual(summary["puzzle_count"], 36)
            self.assertEqual(summary["counts_by_max_hsk_level"], {"1": 12, "7-9": 24})
            self.assertEqual(summary["sha256"], json.loads(path.with_suffix(".summary.json").read_text())["sha256"])
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("SELECT count(*) FROM puzzle_details").fetchone()[0], 36)
                self.assertEqual(db.execute("SELECT SUM(edge_uses) FROM word_usage").fetchone()[0], 144)
                for a, t, l, b, r in db.execute("SELECT answer,top,left,bottom,right FROM puzzle_details"):
                    self.assertEqual(solve(Puzzle((t,), (b,), l, r), self.lexicon()), [a])
            with self.assertRaises(FileExistsError):
                build_database(self.lexicon(), path)
            low = build_database(self.lexicon(), Path(directory) / "low.sqlite", "6")
            self.assertEqual(low["puzzle_count"], 12)


if __name__ == "__main__":
    unittest.main()
