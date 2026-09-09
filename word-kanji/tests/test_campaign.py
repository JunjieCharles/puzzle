import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.export_campaign import arrange, difficulty, digest_value, public_record, VERSION
from scripts.audit_public import inspect_campaign
from toy import toy


def sample(index, group, rank):
    row = {"id": index, "answer": toy(group), "answer_level": "1", "difficulty": (rank,) * 4}
    for offset, side in enumerate(("top", "left", "bottom", "right")):
        row[side] = toy(100 + offset)
        row[f"{side}_level"] = str(rank)
    return row


class CampaignTests(unittest.TestCase):
    def test_spacing_preserves_every_puzzle_and_difficulty_trend(self):
        rows = [sample(group * 3 + repeat, group, repeat + 1) for group in range(40) for repeat in range(3)]
        ordered = arrange(rows, 31)
        self.assertEqual(sorted(row["id"] for row in ordered), list(range(120)))
        last = {}
        for index, row in enumerate(ordered):
            if row["answer"] in last:
                self.assertGreaterEqual(index - last[row["answer"]], 31)
            last[row["answer"]] = index
        self.assertLess(sum(difficulty(r)[0] for r in ordered[:40]), sum(difficulty(r)[0] for r in ordered[-40:]))
        self.assertEqual(ordered, arrange(list(reversed(rows)), 31))

    def test_impossible_spacing_fails_instead_of_silently_relaxing(self):
        with self.assertRaises(ValueError):
            arrange([sample(i, 0, 1) for i in range(3)], 2)

    def test_public_export_does_not_carry_solution_or_internal_ids(self):
        row = sample(92, 0, 1)
        record = public_record(row)
        self.assertEqual(set(record), {"id", "clues", "levels", "difficulty", "salt", "check"})
        self.assertEqual(record["check"], digest_value(record["id"], record["salt"], row["answer"]))
        self.assertNotEqual(record["check"], digest_value(record["id"], record["salt"], toy(1)))
        self.assertNotEqual(record["check"], digest_value("different", record["salt"], row["answer"]))
        self.assertNotEqual(record["check"], public_record(row)["check"])
        message = f"{VERSION}:{record['id']}:{record['salt']}:{row['answer']}"
        self.assertEqual(record["check"], hashlib.sha256(message.encode()).hexdigest())
        self.assertEqual(record["check"], digest_value(record["id"], record["salt"], " " + row["answer"] + "\n"))

    def test_whitelist_rejects_hidden_mapping_and_multi_character_clues(self):
        data = {"version": VERSION, "revision": "a" * 16, "puzzles": [public_record(sample(1, 0, 1))]}
        self.assertEqual(inspect_campaign(data), [])
        modified = copy.deepcopy(data)
        modified["puzzles"][0]["source_id"] = 1
        self.assertTrue(inspect_campaign(modified))
        modified = copy.deepcopy(data)
        modified["puzzles"][0]["clues"]["top"] = toy(0, 1)
        self.assertTrue(inspect_campaign(modified))
        modified = copy.deepcopy(data)
        modified["puzzles"][0]["levels"]["lookup"] = "1"
        self.assertTrue(inspect_campaign(modified))
        modified = copy.deepcopy(data)
        modified["puzzles"][0]["check"] = toy(0)
        self.assertTrue(inspect_campaign(modified))


if __name__ == "__main__":
    unittest.main()
