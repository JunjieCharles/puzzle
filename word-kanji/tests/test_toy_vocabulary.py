import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from vocabulary_policy import allowed, filter_campaign


class ToyVocabularyTests(unittest.TestCase):
    def test_targeted_policy_preserves_neutral_words(self):
        self.assertTrue(all(allowed(w) for w in ("性能", "阴天", "精神", "乳酪", "消毒", "杀菌")))
        self.assertFalse(any(allowed(w) for w in ("色情", "赌博", "自杀", "傻逼")))
        self.assertTrue(allowed("成人"))
        self.assertFalse(any(allowed(w) for w in ("㚻", "㞗", "婬", "打炮", "约炮", "卖身")))

    def test_campaign_checks_edges_and_keeps_only_public_records(self):
        # Artificial rules/words only, not a real puzzle fixture.
        from unittest.mock import patch
        record = {"id": "synthetic", "salt": "salt", "clues": {"top": "A", "bottom": "B", "left": "C", "right": "D"},
                  "check": hashlib.sha256(b"version:synthetic:salt:X").hexdigest()}
        other = dict(record, id="other", check=hashlib.sha256(b"version:other:salt:Y").hexdigest())
        data = {"version": "version", "revision": "old", "puzzles": [record, other]}
        words = ["X", "Y", "AX", "XB", "CX", "XD", "AY", "YB", "CY", "YD"]
        with patch("vocabulary_policy.allowed", side_effect=lambda w: w != "AX"):
            result = filter_campaign(data, words, 1)
        self.assertEqual(result["puzzles"], [other])
        self.assertNotEqual(result["revision"], "old")
        self.assertEqual(len(data["puzzles"]), 2)

    def test_two_campaign_filters_middle_word_edges_and_clues(self):
        # Artificial alphabet and rules; no real puzzle/solution correspondence.
        from unittest.mock import patch
        def fixture(identifier, value, symbols):
            a, b, c, d, e, f = symbols
            return {"id": identifier, "salt": "salt",
                    "clues": {"top": [a, b], "bottom": [c, d], "left": e, "right": f},
                    "check": hashlib.sha256(f"version:{identifier}:salt:{value}".encode()).hexdigest()}
        first = fixture("first", "XY", "ABCDEF")
        second = fixture("second", "ZW", "GHIJKL")
        data = {"version": "version", "revision": "old", "puzzles": [first, second]}
        words = ["XY", "AX", "BY", "XC", "YD", "EX", "YF",
                 "ZW", "GZ", "HW", "ZI", "WJ", "KZ", "WL"]
        for excluded in ("XY", "AX", "BY", "XC", "YD", "EX", "YF", *"ABCDEF"):
            with self.subTest(excluded=excluded), patch("vocabulary_policy.allowed", side_effect=lambda w: w != excluded):
                result = filter_campaign(data, words, 2)
                self.assertEqual(result["puzzles"], [second])
                self.assertNotEqual(result["revision"], data["revision"])
        with patch("vocabulary_policy.allowed", return_value=True):
            self.assertEqual(filter_campaign(data, words, 2), data)
