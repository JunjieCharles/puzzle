"""Assemble a separate Toy package from reviewed shared assets and Toy adapters."""
import argparse
from pathlib import Path
import re
import hashlib
import json

from build_site import ASSETS, PUBLIC
from audit_public import inspect_file
from vocabulary_policy import REVISION, encode, filter_endless, filter_words, filter_campaign

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
    # Editorial changes are confined to this build; preserve the original web sequence.
    vocabulary = json.loads(payloads["endless-lexicon.json"])
    payloads["endless-lexicon.json"] = encode(filter_endless(vocabulary))
    hints = json.loads(payloads["hsk-two-words.json"])
    payloads["hsk-two-words.json"] = encode(dict(hints, words=filter_words(hints["words"])))
    for name, size in (("campaign.json", 1), ("campaign-two.json", 2)):
        payloads[name] = encode(filter_campaign(json.loads(payloads[name]), vocabulary["common"], size))
    engine = payloads["endless-engine.js"].decode("utf-8")
    payloads["endless-engine.js"] = replace_once(engine, r'export const REVISION = "endless-v1";',
                                               f'export const REVISION = "{REVISION}";').encode("utf-8")
    worker = payloads["endless-worker.js"].decode("utf-8")
    digest = hashlib.sha256(payloads["endless-lexicon.json"]).hexdigest()
    payloads["endless-worker.js"] = replace_once(worker, r'const VOCABULARY_SHA256 = "[a-f0-9]+";',
                                               f'const VOCABULARY_SHA256 = "{digest}";').encode("utf-8")
    notice = payloads["NOTICE.txt"].decode("utf-8")
    notice = notice.replace("complete generic one- and two-character vocabulary exported for", "editorially filtered generic one- and two-character vocabulary exported for")
    payloads["NOTICE.txt"] = (notice + "\nToy edition: editorial vocabulary exclusions; affected campaign records omitted.\n").encode("utf-8")
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
