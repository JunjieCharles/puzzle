"""Artificial symbols for solver tests; these are NOT HSK words or published puzzles."""


def toy(*indices):
    return "".join(chr(0x3400 + index) for index in indices)
