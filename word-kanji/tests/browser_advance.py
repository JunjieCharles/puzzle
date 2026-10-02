"""Actual fill progression/restart across all modes, including reduced-motion settings."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_endless import fixture, ready

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_campaign import sample
from toy import toy
from generator import Lexicon
from scripts.export_campaign import public_record, VERSION
from scripts.generate_two import public_payload, puzzle_from


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8017/puzzle/word-kanji/")
    url = parser.parse_args().url.rstrip("/") + "/"
    one = {"version": VERSION, "revision": "c" * 16, "puzzles": [public_record(sample(i, i, 1)) for i in range(3)]}
    rows, words = [], set()
    for n in range(3):
        chars = [chr(0x5400 + n * 8 + i) for i in range(8)]
        value, clues = "".join(chars[:2]), chars[2:]
        words.update(w for _, w in puzzle_from(clues).edge_words(value))
        rows.append({"answer": value, "clues": clues, "difficulty": [1] * 6})
    two = public_payload(rows, Lexicon([{"word": w, "level": "1"} for w in words], set()))
    payload = json.dumps(fixture(), ensure_ascii=False).encode()
    worker = (ROOT / "public" / "endless-worker.js").read_text(encoding="utf-8")
    worker = re.sub(r'const VOCABULARY_SHA256 = "[a-f0-9]+"', 'const VOCABULARY_SHA256 = "' + hashlib.sha256(payload).hexdigest() + '"', worker)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for motion in ("no-preference", "reduce"):
            context = browser.new_context(reduced_motion=motion)
            context.route("**/campaign.json", lambda r: r.fulfill(json=one))
            context.route("**/campaign-two.json", lambda r: r.fulfill(json=two))
            context.route("**/endless-lexicon.json", lambda r: r.fulfill(body=payload, content_type="application/json"))
            context.route("**/endless-worker.js", lambda r: r.fulfill(body=worker, content_type="text/javascript"))
            page = context.new_page(); errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            for route, size, endless in (("play/1", 1, False), ("play-two/1", 2, False), ("endless-one", 1, True), ("endless-two", 2, True)):
                page.goto(url + "#" + route)
                for level in (1, 2):
                    ready(page, level)
                    if endless:
                        value = page.evaluate("""async ({size, level}) => {
                          const {Vocabulary, EndlessSequence} = await import('./endless-engine.js');
                          const v = new Vocabulary(await (await fetch('./endless-lexicon.json')).json());
                          const s = new EndlessSequence(v,size); let generated;
                          for(let n=0;n<level;n++) generated=s.next();
                          return generated.solution;
                        }""", {"size": size, "level": level})
                    else:
                        value = toy(level - 1) if size == 1 else rows[level - 1]["answer"]
                    page.locator("#entry").fill(value)
                    page.locator("#submit").click()
                    page.locator("#next").wait_for(state="visible")
                    measurements = page.evaluate("""async () => {
                      const sample = () => {
                        const style = getComputedStyle(document.querySelector('#next span'),'::after');
                        return {name:style.animationName,duration:style.animationDuration,scale:new DOMMatrixReadOnly(style.transform).a};
                      };
                      await new Promise(r=>setTimeout(r,100)); const first=sample();
                      await new Promise(r=>setTimeout(r,300)); return [first,sample()];
                    }""")
                    first, later = measurements
                    assert first["name"] == later["name"] == "advance-fill", (motion, route, measurements)
                    assert first["duration"] == later["duration"] == "0.9s", (motion, route, measurements)
                    assert 0 < first["scale"] < 0.5 and first["scale"] + 0.15 < later["scale"] < 0.9, (motion, route, measurements)
                    ready(page, level + 1)
                    assert not page.locator("#next").is_visible()
            assert not errors, errors
            context.close()
        browser.close()
    print("Advance fill passed: all four modes, consecutive passes, normal/reduced motion.")


if __name__ == "__main__":
    main()
