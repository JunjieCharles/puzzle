"""Package only reviewed public assets for the configured GitHub Pages base path."""
import argparse
from pathlib import Path
import shutil

from audit_public import inspect_file

PUBLIC = Path(__file__).resolve().parents[1] / "public"
ASSETS = ("index.html", "app.js", "style.css", "save-code.js", "progress.js", "platform.js", "campaign.json", "campaign-two.json", "hsk-two-words.json",
          "coin.svg", "one-standard.svg", "two-standard.svg", "NOTICE.txt")


def build_site(output, base_path="", public=PUBLIC):
    base_path = base_path.rstrip("/")
    if base_path not in ("", "/puzzle"):
        raise ValueError("To serve /puzzle/word-kanji, use the puzzle project site or a root/custom-domain site")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; refusing to overwrite existing files")
    for name in ASSETS:
        source = public / name
        if source.is_symlink() or not source.is_file() or inspect_file(name, source.read_bytes()):
            raise ValueError(f"Invalid public asset: {name}")
    relative = Path("word-kanji") if base_path else Path("puzzle/word-kanji")
    target = output / relative
    target.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(public / name, target / name)
    href = relative.as_posix() + "/"
    (output / "index.html").write_text(
        f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=./{href}">'
        f'<title>Puzzle</title><a href="./{href}">Puzzle</a></html>\n', encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-path", default="")
    args = parser.parse_args()
    print(build_site(args.output, args.base_path))
