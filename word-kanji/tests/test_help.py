"""Check the explicitly authorized teaching examples, never real-puzzle answer fixtures."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon, Puzzle, solve
from scripts.export_campaign import is_teaching_puzzle


class TeachingMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.panel = None
        self.classes = []
        self.cells = {"one": {}, "two": {}}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section" and attrs.get("id", "").startswith("help-panel-"):
            self.panel = attrs["id"].split("-")[-1]
        if tag == "span" and self.panel:
            self.classes = attrs.get("class", "").split()

    def handle_data(self, text):
        if self.panel and self.classes and text.strip():
            for name in self.classes:
                self.cells[self.panel][name] = text.strip()

    def handle_endtag(self, tag):
        if tag == "span":
            self.classes = []
        if tag == "section":
            self.panel = None


class HelpTests(unittest.TestCase):
    def test_dedicated_two_example_is_valid_and_not_a_playable_answer_mapping(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        parser = TeachingMarkup(); parser.feed(html)
        c = parser.cells["two"]
        # Locate the first fill independently, since the second fill shares its base class.
        first = html.split('id="help-panel-two"', 1)[1].split('<span class="help-answer">', 1)[1].split("<", 1)[0]
        teaching = first + c["help-answer-two"]
        puzzle = Puzzle((c["top"], c["help-top-two"]), (c["bottom"], c["help-bottom-two"]), c["left"], c["right"])
        lexicon = Lexicon.load()
        self.assertEqual(solve(puzzle, lexicon), [teaching])
        self.assertTrue(puzzle.distinct(teaching))
        self.assertTrue(any(word not in lexicon.records for _, word in puzzle.edge_words(teaching)))
        def equivalent(clues):
            return (set((clues["top"][0], clues["left"])) == set((puzzle.top[0], puzzle.left))
                    and clues["top"][1] == puzzle.top[1] and clues["bottom"][0] == puzzle.bottom[0]
                    and set((clues["bottom"][1], clues["right"])) == set((puzzle.bottom[1], puzzle.right)))
        two = json.loads((ROOT / "public" / "campaign-two.json").read_text(encoding="utf-8"))
        self.assertFalse(any(equivalent(row["clues"]) for row in two["puzzles"]))
        one = json.loads((ROOT / "public" / "campaign.json").read_text(encoding="utf-8"))
        self.assertFalse(any(is_teaching_puzzle(row["clues"]) for row in one["puzzles"]))
