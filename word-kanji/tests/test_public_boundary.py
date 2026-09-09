import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage import PRIVATE_ROOT, REPOSITORY_ROOT, private_output
from scripts.audit_public import inspect_file, inspect_json


class PublicBoundaryTests(unittest.TestCase):
    def test_private_default_outside_repository(self):
        self.assertNotIn(REPOSITORY_ROOT, PRIVATE_ROOT.parents)
        self.assertNotEqual(PRIVATE_ROOT, REPOSITORY_ROOT)

    def test_private_output_rejects_repository_paths(self):
        for path in (ROOT / "public" / "puzzles.json", ROOT / "datasets" / "new.sqlite", REPOSITORY_ROOT):
            with self.assertRaises(ValueError):
                private_output(path)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(private_output(Path(directory) / "puzzles.sqlite"), Path(directory).resolve() / "puzzles.sqlite")

    def test_answer_mapping_and_private_artifacts_rejected(self):
        self.assertTrue(inspect_json({"puzzles": [{"answer": "placeholder"}]}))
        self.assertTrue(inspect_json({"nested": {"edge_words": []}}))
        self.assertTrue(inspect_file("word-kanji/examples/puzzles.md", b""))
        self.assertTrue(inspect_file("word-kanji/datasets/test.sqlite", b""))

    def test_wordlists_and_aggregate_reports_allowed(self):
        self.assertEqual(inspect_json({"words": [{"word": "placeholder", "level": "1"}]}), [])
        self.assertEqual(inspect_json({"puzzle_count": 1407, "answers_with_puzzles": 587}), [])


if __name__ == "__main__":
    unittest.main()
