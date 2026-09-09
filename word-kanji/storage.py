"""Keep answer-bearing artifacts outside the Git repository."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = next((p for p in (PROJECT_ROOT, *PROJECT_ROOT.parents) if (p / ".git").exists()), PROJECT_ROOT.parent)
PRIVATE_ROOT = Path(os.environ.get(
    "WORD_KANJI_PRIVATE_DIR",
    str(REPOSITORY_ROOT.with_name(REPOSITORY_ROOT.name + "-private") / PROJECT_ROOT.name),
)).expanduser().resolve()


def private_output(path):
    path = Path(path).expanduser().resolve()
    if path == REPOSITORY_ROOT or REPOSITORY_ROOT in path.parents:
        raise ValueError("Answer-bearing output must be outside the repository; use WORD_KANJI_PRIVATE_DIR or an external --output path")
    return path
