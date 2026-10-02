"""Assemble a separate Toy package from reviewed shared assets and Toy adapters."""
import argparse
from pathlib import Path
import re

from build_site import ASSETS, PUBLIC
from audit_public import inspect_file

TOY = PUBLIC.parent / "toy"


def replace_once(text, pattern, replacement):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.S)
    if count != 1:
        raise ValueError(f"Shared template changed: expected one match for {pattern}")
    return result


def build_toy(output):
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output directory must be empty")
    payloads = {}
    for name in ASSETS:
        if name in ("save-code.js", "platform.js"):
            continue
        source = PUBLIC / name
        if source.is_symlink():
            raise ValueError("Symlink assets are not allowed")
        payloads[name] = source.read_bytes()
    app = payloads["app.js"].decode("utf-8")
    app = replace_once(app, r"// WEB-SAVE-BEGIN.*?// WEB-SAVE-END", "")
    payloads["app.js"] = app.encode("utf-8")
    html = payloads["index.html"].decode("utf-8")
    html = replace_once(html, r'<button id="save-open".*?</button>', (TOY / "toolbar.html").read_text(encoding="utf-8"))
    html = replace_once(html, r'  <div id="save-warning".*?(?=  <dialog id="help-dialog")', (TOY / "panels.html").read_text(encoding="utf-8"))
    html = html.replace('<script type="module" src="./app.js?v=progress-2"></script>',
                        '<script defer src="https://s1.hdslb.com/bfs/seed/toy/app/sdk/toy-sdk.js"></script>\n'
                        '  <link rel="stylesheet" href="./toy.css">\n'
                        '  <script type="module" src="./app.js?v=toy-1"></script>')
    payloads["index.html"] = html.encode("utf-8")
    for name in ("platform.js", "cloud.js", "toy.css"):
        source = TOY / name
        if source.is_symlink():
            raise ValueError("Symlink assets are not allowed")
        payloads[name] = source.read_bytes()
    for name, data in payloads.items():
        errors = inspect_file(name, data)
        if errors:
            raise ValueError(f"Invalid Toy asset {name}: {errors}")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(build_toy(parser.parse_args().output))
