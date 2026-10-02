"""Browser integration checks using artificial vocabulary; no production solutions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    words = set()
    for size, offset in ((1, 0x3400), (2, 0x4400)):
        for n in range(105):
            c = [chr(offset + n * 8 + i) for i in range(8)]
            local = [c[0], c[2] + c[0], c[3] + c[0], c[0] + c[4], c[0] + c[5]] if size == 1 else [
                c[0] + c[1], c[2] + c[0], c[3] + c[1], c[0] + c[4], c[1] + c[5], c[6] + c[0], c[1] + c[7]]
            words.update(local)
    return {"version": "endless-lexicon-v1", "common": sorted(words), "broad": sorted(words)}


def ready(page, level):
    page.wait_for_function("n => document.querySelector('#level-title').textContent === `第 ${n} 关` && !document.querySelector('#entry').disabled", arg=level)


def clue_text(page):
    return page.locator("#board .clue").all_text_contents()


def solve(page, size, level):
    value = page.evaluate("""async ({size, level}) => {
      const {Vocabulary, EndlessSequence} = await import('./endless-engine.js');
      const data = await (await fetch('./endless-lexicon.json')).json();
      const sequence = new EndlessSequence(new Vocabulary(data), size);
      let generated; for (let n=0;n<level;n++) generated=sequence.next();
      return generated.solution;
    }""", {"size": size, "level": level})
    page.locator("#entry").fill(value)
    page.evaluate("""() => {
      window.transitionCheck = { blank: false, loading: false };
      window.transitionObserver = new MutationObserver(() => {
        transitionCheck.blank ||= !document.querySelector('#top').textContent;
        transitionCheck.loading ||= document.querySelector('#level-count').textContent.includes('准备题目');
      });
      transitionObserver.observe(document.querySelector('#play'), {subtree:true,childList:true,attributes:true});
    }""")
    page.locator("#submit").click()
    if level == 1:
        # The synthetic Worker delays level 2: keep the completed board until ready.
        page.wait_for_timeout(1000)
        assert page.locator("#level-title").inner_text() == "第 1 关"
        assert page.locator("#entry").input_value() == value[0]
        assert page.locator("#entry").get_attribute("readonly") is not None
        assert "departing" not in page.locator("#puzzle-form").get_attribute("class")
    ready(page, level + 1)
    state = page.evaluate("() => { transitionObserver.disconnect(); return transitionCheck; }")
    assert state == {"blank": False, "loading": False}, state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8017/puzzle/word-kanji/")
    args = parser.parse_args()
    url = args.url.rstrip("/") + "/"
    payload = json.dumps(fixture(), ensure_ascii=False).encode()
    worker = (ROOT / "public" / "endless-worker.js").read_text(encoding="utf-8")
    worker = re.sub(r'const VOCABULARY_SHA256 = "[a-f0-9]+"', 'const VOCABULARY_SHA256 = "' + hashlib.sha256(payload).hexdigest() + '"', worker)
    worker = worker.replace("latest.set(size, { level, puzzle });", "if (level === 2) await new Promise(resolve => setTimeout(resolve, 1400));\n    latest.set(size, { level, puzzle });")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.route("**/endless-lexicon.json", lambda r: r.fulfill(body=payload, content_type="application/json"))
        context.route("**/endless-worker.js", lambda r: r.fulfill(body=worker, content_type="text/javascript"))
        page = context.new_page(); errors = []
        page.emulate_media(reduced_motion="reduce")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.locator("#endless-start").click()
        page.locator("#endless-start-one").click()
        ready(page, 1)
        original = clue_text(page)
        assert not page.locator(".level-nav").is_visible()
        assert not page.locator("#progress").is_visible()
        page.goto(url + "#endless-one/999")
        ready(page, 1)
        assert page.url.endswith("#endless-one") and clue_text(page) == original
        page.reload(); ready(page, 1)
        assert clue_text(page) == original and page.locator("#entry").input_value() == ""
        page.locator("#entry").fill(chr(0x6500)); page.locator("#submit").click()
        page.wait_for_function("document.querySelector('#feedback').classList.contains('error')")
        assert page.locator("#level-title").inner_text() == "第 1 关"
        solve(page, 1, 1)
        second = clue_text(page)
        page.reload(); ready(page, 2)
        assert clue_text(page) == second
        page.locator("#play .back").click()
        page.locator("#endless-start-two").click(); ready(page, 1)
        assert not page.locator("#entry-two").is_disabled()
        solve(page, 2, 1)
        for width, height in [(1280, 900), (390, 844), (320, 568), (844, 390)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1")
            board = page.locator("#board").bounding_box()
            heading = page.locator("#play .view-top").bounding_box()
            assert board["y"] >= heading["y"] + heading["height"]
        page.set_viewport_size({"width": 390, "height": 844})
        screenshot = Path(tempfile.gettempdir()) / "word-kanji-endless-synthetic.png"
        page.screenshot(path=str(screenshot))
        # Export/import both sequential modes and verify a fresh session can reconstruct them.
        page.locator("#save-open").click(); page.locator("#save-export").click()
        page.wait_for_function("document.querySelector('#save-code').value.startsWith('HT101-2.')")
        code = page.locator("#save-code").input_value()
        records = page.evaluate("Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.includes('endless')).map(([k,v])=>[k,JSON.parse(v)]))")
        assert len(records) == 2
        assert all(set(r) == {"revision", "next"} and r["next"] == 2 for r in records.values())
        page.evaluate("localStorage.clear()")
        page.reload()
        page.locator("#save-open").click(); page.locator("#save-code").fill(code); page.locator("#save-import").click()
        page.wait_for_function("document.querySelector('#save-status').textContent.includes('已导入')")
        page.locator("#save-dialog .help-close").click(); ready(page, 2)
        # Corrupt one known mode must not prevent the campaign or the other mode from opening.
        page.evaluate("localStorage.setItem('word-kanji:endless-one-standard:v1', JSON.stringify({revision:'unknown',next:9}))")
        page.goto(url + "#levels"); page.locator("#level-grid button").first.wait_for()
        page.goto(url + "#endless-one")
        page.wait_for_function("document.querySelector('#feedback').textContent.includes('存档')")
        assert page.locator("#entry").is_disabled()
        page.goto(url + "#endless-two"); ready(page, 2)
        # A failed vocabulary fetch is retryable, with no fallback to different data.
        context.unroute("**/endless-lexicon.json")
        context.route("**/endless-lexicon.json", lambda r: r.fulfill(status=503, body="unavailable"))
        page.reload(); page.locator("#retry").wait_for(state="visible")
        assert page.locator("#entry").is_disabled()
        context.unroute("**/endless-lexicon.json")
        context.route("**/endless-lexicon.json", lambda r: r.fulfill(body=payload, content_type="application/json"))
        page.locator("#retry").click(); ready(page, 2)
        # Cancel a deep replay by leaving; returning must still recover the same sequence.
        page.evaluate("localStorage.setItem('word-kanji:endless-two-standard:v1', JSON.stringify({revision:'endless-v1',next:10000}))")
        page.reload(); page.locator("#play .back").click()
        page.locator("#endless-types-title").wait_for()
        page.locator("#endless-start-two").click(); ready(page, 10000)
        recovered = clue_text(page)
        page.reload(); ready(page, 10000)
        assert clue_text(page) == recovered
        assert not errors, errors
        browser.close()
        print("Endless browser checks passed; synthetic screenshot: " + str(screenshot))


if __name__ == "__main__":
    main()
