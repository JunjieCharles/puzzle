"""Synthetic exhaustive checks; no real answer mappings in fixtures."""
import copy
import itertools
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generator import Lexicon, solve
from matching import maximum_matching
from difficulty import word_counts
from scripts.generate_two import hardest, has_unique, puzzle_from, clue_score, select, public_payload, clue_resources, exclude_used_clues
from scripts.estimate_space import IndexedAudit
from scripts.audit_public import inspect_two_campaign, inspect_json
from scripts.generate_two import order_difficulty, arrange_selected
from collections import Counter


def all_matchings(rows, used=frozenset()):
    if not rows:
        yield []
        return
    first, rest = rows[0], rows[1:]
    yield from all_matchings(rest, used)
    if not used.intersection(first["answer"]):
        for chosen in all_matchings(rest, used | set(first["answer"])):
            yield [first] + chosen


class TwoTests(unittest.TestCase):
    def test_minimax_uses_the_known_answer_character_in_the_correct_direction(self):
        chars = [chr(0x3400 + i) for i in range(8)]
        answer, clues = ''.join(chars[:2]), chars[2:]
        starts = Counter({c: 100 for c in chars})
        ends = Counter(starts)
        starts[clues[0]], starts[clues[4]], ends[clues[2]] = 12, 8, 11
        starts[clues[1]], ends[clues[3]], ends[clues[5]] = 23, 20, 29
        # A first: max(8,min(20,10))=10; B first: max(20,min(8,2))=20.
        starts[answer[0]], ends[answer[1]] = 10, 2
        self.assertEqual(order_difficulty(answer, clues, (starts, ends)), 10)
        # Reversing the easier entry: A first=30; B first=max(7,min(30,9))=9.
        starts[clues[0]], starts[clues[4]], ends[clues[2]] = 30, 35, 40
        starts[clues[1]], ends[clues[3]], ends[clues[5]] = 7, 15, 25
        starts[answer[0]], ends[answer[1]] = 2, 9
        self.assertEqual(order_difficulty(answer, clues, (starts, ends)), 9)
        # The unused directions must not influence the result.
        ends[answer[0]], starts[answer[1]] = 1, 1
        self.assertEqual(order_difficulty(answer, clues, (starts, ends)), 9)

    def test_order_ties_keep_old_selection_order_and_do_not_mutate_rows(self):
        chars = [chr(0x3400 + i) for i in range(8)]
        counts = (Counter({c: 8 for c in chars}), Counter({c: 8 for c in chars}))
        rows = [{"answer": ''.join(chars[:2]), "clues": chars[2:], "difficulty": [n] * 6} for n in (5, 3)]
        original = copy.deepcopy(rows)
        self.assertEqual([r["difficulty"][0] for r in arrange_selected(rows, counts)], [3, 5])
        self.assertEqual(rows, original)

    def test_word_guess_identity_preserves_opposite_missing_position(self):
        chars = [chr(0x3400 + i) for i in range(8)]
        answer, clues = ''.join(chars[:2]), chars[2:]
        resources = clue_resources(answer, clues)
        self.assertEqual(len(resources), 7)
        self.assertIn((answer, 2), resources)
        domains = [{c} for c in clues]
        # The same word with the other character missing is a different clue.
        word = clues[0] + answer[0]
        self.assertEqual(exclude_used_clues(answer, domains, {(word, 0)})[0], domains[0])
        self.assertFalse(exclude_used_clues(answer, domains, {(word, 1)})[0])
        outgoing = answer[0] + clues[2]
        self.assertEqual(exclude_used_clues(answer, domains, {(outgoing, 1)})[2], domains[2])
        self.assertFalse(exclude_used_clues(answer, domains, {(outgoing, 0)})[2])

    def test_cardinality_then_difficulty_against_exhaustive_matchings(self):
        rng = random.Random(901)
        for _ in range(100):
            rows = [{"answer": chr(0x3400+a) + chr(0x3400+b),
                     "clues": (str(a), str(b)), "difficulty": (rng.randrange(1, 20),) * 6}
                    for a in range(6) for b in range(a) if rng.random() < .5]
            priority = sorted(rows, key=lambda r: (tuple(-v for v in r["difficulty"]), r["clues"], r["answer"]))
            def score(chosen):
                # Like one-cell selection, deterministic same-score ties are
                # settled before the next priority item; this is not score sum.
                return len(chosen), tuple(int(row in chosen) for row in priority)
            self.assertEqual(score(select(rows)), max(map(score, all_matchings(rows))))

    def test_existence_and_hardest_against_all_clue_combinations(self):
        rng = random.Random(85)
        chars = [chr(0x3400+i) for i in range(10)]
        successes = 0
        for _ in range(80):
            words = {a+b for a in chars for b in chars if rng.random() < .5}
            answer = ''.join(chars[:2]); words.add(answer)
            lex = Lexicon([{"word": w, "level": "1"} for w in words], set())
            audit, counts = IndexedAudit(lex), word_counts(words)
            domains = []
            for pos, incoming in [(0, True), (1, True), (0, False), (1, False)]:
                available = sorted((audit.before if incoming else audit.after)[answer[pos]] - set(answer))
                domains.append(set(rng.sample(available, min(3, len(available)))))
            domains += [domains[0], domains[3]]
            valid = [clues for clues in itertools.product(*domains)
                     if len(set(clues)) == 6 and solve(puzzle_from(clues), lex) == [answer]]
            exists = all(domains) and has_unique(answer, domains, audit)
            self.assertEqual(bool(exists), bool(valid))
            if valid:
                successes += 1
                row = hardest(answer, domains, audit, counts)
                self.assertEqual(row["difficulty"], max(clue_score(c, counts) for c in valid))
        self.assertGreater(successes, 10)

    def test_public_whitelist_and_repeat_export(self):
        chars = [chr(0x3400+i) for i in range(8)]
        answer, clues = ''.join(chars[:2]), chars[2:]
        p = puzzle_from(clues)
        lex = Lexicon([{"word": w, "level": "1"} for _, w in p.edge_words(answer)], set())
        rows = [{"answer": answer, "clues": clues, "difficulty": (1, 1, 1, 1, 1, 1)}]
        first = public_payload(rows, lex)
        self.assertEqual(public_payload(rows, lex, first), first)
        self.assertFalse(inspect_two_campaign(first))
        self.assertFalse(inspect_json(first))
        for key, value in [("answer", answer), ("source_id", 123), ("path", [1, 2])]:
            bad = copy.deepcopy(first); bad["puzzles"][0][key] = value
            self.assertTrue(inspect_two_campaign(bad))
        bad = copy.deepcopy(first); bad["puzzles"][0]["clues"]["top"] = [answer, chars[4]]
        self.assertTrue(inspect_two_campaign(bad))


if __name__ == "__main__":
    unittest.main()
