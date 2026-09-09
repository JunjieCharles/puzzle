"""Directional two-character word counts over the expanded vocabulary."""
from collections import Counter
from generator import Lexicon, is_hanzi_word

MODEL = "broad-directional-word-count-lexicographic-v2"


def word_counts(words):
    words = {word for word in words if len(word) == 2 and is_hanzi_word(word)}
    return Counter(word[0] for word in words), Counter(word[1] for word in words)


def load_counts():
    return word_counts(Lexicon.load().broad_two)


def clue_score(row, counts):
    starts, ends = counts
    return tuple(sorted((starts[row["top"]], starts[row["left"]], ends[row["bottom"]], ends[row["right"]])))


def reference_scores(words, counts):
    starts, ends = counts
    return ({ref: starts[word[0]] for ref, word in words.items()},
            {ref: ends[word[-1]] for ref, word in words.items()})


def reference_score(refs, scores, base=None):
    starts, ends = scores
    top, left, bottom, right = refs
    values = sorted((starts[top], starts[left], ends[bottom], ends[right]))
    if base is None:
        base = max(max(starts.values(), default=0), max(ends.values(), default=0)) + 1
    score = 0
    for value in values:
        score = score * base + value
    return score
