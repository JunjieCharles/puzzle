"""Two-cell UI and legacy-save regression checks with synthetic puzzles only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generator import Lexicon
from scripts.generate_two import public_payload, puzzle_from
from scripts.export_campaign import public_record, VERSION
from test_campaign import sample
from toy import toy
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8001/puzzle/word-kanji/")
    args = parser.parse_args()
    url = args.url.rstrip("/") + "/"
    rows = []
    words = set()
    for n in range(3):
        chars = [chr(0x3400 + n * 8 + i) for i in range(8)]
        answer, clues = ''.join(chars[:2]), chars[2:]
        words.update(w for _, w in puzzle_from(clues).edge_words(answer))
        rows.append({"answer": answer, "clues": clues, "difficulty": [n + 1] * 6})
    lex = Lexicon([{"word": w, "level": "1"} for w in words], set())
    two = public_payload(rows, lex)
    one = {"version": VERSION, "revision": "c" * 16, "puzzles": [public_record(sample(i, i, 1)) for i in range(3)]}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.route("**/campaign.json", lambda r: r.fulfill(json=one))
        context.route("**/campaign-two.json", lambda r: r.fulfill(json=two))
        context.route("**/hsk-two-words.json", lambda r: r.fulfill(json={"version": "hsk-two-words-v1", "words": sorted(words)}))
        page = context.new_page(); errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url + "#types")
        page.locator("#start-two").click()
        page.locator("#level-grid button").first.click()
        page.wait_for_function("!document.querySelector('#entry-two').disabled")
        assert page.url.endswith("#play-two/1")
        for width, height in [(1280,900), (390,844), (320,568), (844,390)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1")
            assert page.locator("#entry").bounding_box()["x"] < page.locator("#entry-two").bounding_box()["x"]
        page.set_viewport_size({"width":390,"height":844})
        assert not page.locator("#entry").get_attribute("placeholder")
        assert not page.locator("#entry-two").get_attribute("placeholder")
        # IME composition must keep the whole phrase until the user commits it.
        page.locator("#entry").evaluate("""(input, word) => {
            input.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
            input.value = word;
            input.dispatchEvent(new InputEvent('input', {bubbles:true,isComposing:true}));
        }""", rows[0]["answer"])
        assert page.locator("#entry").input_value() == rows[0]["answer"]
        assert not page.locator("#entry-two").input_value()
        page.locator("#entry").evaluate("""input => {
            input.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true}));
            input.dispatchEvent(new InputEvent('input', {bubbles:true,isComposing:false}));
        }""")
        assert page.locator("#entry").input_value() == rows[0]["answer"][0]
        assert page.locator("#entry-two").input_value() == rows[0]["answer"][1]
        # Pasting a phrase into either field fills both; Unicode characters stay intact.
        pasted = chr(0x20000) + rows[0]["answer"]
        page.locator("#entry-two").fill(pasted)
        assert page.locator("#entry").input_value() == pasted[0]
        assert page.locator("#entry-two").input_value() == pasted[1]
        page.locator("#entry").press("ArrowRight")
        assert page.locator("#entry-two").evaluate("e => e === document.activeElement")
        page.locator("#entry-two").press("ArrowRight")
        assert page.locator("#entry-two").evaluate("e => e === document.activeElement")
        page.locator("#entry-two").press("ArrowLeft")
        assert page.locator("#entry").evaluate("e => e === document.activeElement")
        page.locator("#entry").evaluate("""input => {
            input.dispatchEvent(new KeyboardEvent('keydown', {
                key:'ArrowRight',bubbles:true,cancelable:true,isComposing:true}));
        }""")
        assert page.locator("#entry").evaluate("e => e === document.activeElement")
        assert page.locator("#entry").input_value() == pasted[0]
        assert page.locator("#entry-two").input_value() == pasted[1]
        page.locator("#entry").press("ArrowRight")
        page.locator("#entry-two").press("Backspace")
        assert not page.locator("#entry-two").input_value()
        assert page.locator("#entry").input_value() == pasted[0]
        page.locator("#entry-two").press("Backspace")
        assert not page.locator("#entry").input_value()
        assert page.locator("#entry").evaluate("e => e === document.activeElement")
        page.locator("#entry").fill(pasted[0])
        page.locator("#entry-two").evaluate("""input => {
            input.dispatchEvent(new InputEvent('beforeinput', {
                bubbles:true,cancelable:true,inputType:'deleteContentBackward',isComposing:true}));
        }""")
        assert page.locator("#entry").input_value() == pasted[0]
        page.locator("#entry-two").evaluate("""input => {
            input.dispatchEvent(new InputEvent('beforeinput', {
                bubbles:true,cancelable:true,inputType:'deleteContentBackward'}));
        }""")
        assert not page.locator("#entry").input_value()
        assert page.locator("#entry").evaluate("e => e === document.activeElement")
        page.locator("#entry").fill(rows[0]["answer"][0])
        page.locator("#submit").click()
        assert page.locator("#feedback").inner_text()
        assert page.evaluate("localStorage.length") == 0
        page.locator("#entry").fill(rows[0]["answer"])
        page.locator("#submit").click()
        page.wait_for_url("**/#play-two/2")
        saved_two = page.evaluate("localStorage.getItem('word-kanji:campaign-two:v1')")
        assert json.loads(saved_two)["completed"] == 1
        assert page.evaluate("localStorage.getItem('word-kanji:campaign:v1')") is None
        page.reload()
        page.wait_for_function("!document.querySelector('#entry-two').disabled")
        page.locator("#previous").click()
        page.locator("#reveal").click()
        page.locator("#hide-answer").wait_for(state="visible")
        assert page.locator("#entry").input_value() + page.locator("#entry-two").input_value() == rows[0]["answer"]
        page.locator("#hide-answer").click()
        assert not page.locator("#entry").input_value() and not page.locator("#entry-two").input_value()
        assert page.evaluate("localStorage.getItem('word-kanji:campaign-two:v1')") == saved_two

        # A genuine v1 one-mode code remains valid, including while playing two-cell mode.
        old_code = page.evaluate("""async () => (await import('./save-code.js')).encodeSave({
          'campaign-one-standard': {revision:'cccccccccccccccc',completed:2}})""")
        page.locator("#save-open").click(); page.locator("#save-code").fill(old_code)
        page.locator("#save-import").click()
        page.wait_for_function("document.querySelector('#levels-count').textContent === '2 / 3'")
        assert page.url.endswith("#levels")
        assert page.evaluate("localStorage.getItem('word-kanji:campaign-two:v1')") == saved_two
        page.locator("#save-export").click()
        page.wait_for_function("old => document.querySelector('#save-code').value !== old", arg=old_code)
        combined = page.locator("#save-code").input_value()
        decoded = page.evaluate("async c => (await import('./save-code.js')).decodeSave(c)", combined)
        assert decoded["campaign-one-standard"]["completed"] == 2
        assert decoded["campaign-two-standard"]["completed"] == 1
        before = page.evaluate("({...localStorage})")
        invalid = page.evaluate("""async revision => (await import('./save-code.js')).encodeSave({
          'campaign-one-standard': {revision:'cccccccccccccccc',completed:3},
          'campaign-two-standard': {revision,completed:999}})""", two["revision"])
        page.locator("#save-code").fill(invalid); page.locator("#save-import").click()
        page.wait_for_function("!document.querySelector('#save-import').disabled")
        assert page.evaluate("({...localStorage})") == before
        page.keyboard.press("Escape")
        page.goto(url + "#types"); page.locator("#start-two").click()
        page.locator("#levels .back").click(); page.locator("#start").click()
        page.wait_for_url("**/#levels")
        page.locator("#level-grid button").first.click()
        assert page.locator("#entry-two").is_hidden()
        page.locator("#entry").fill(toy(0)); page.locator("#submit").click()
        page.wait_for_url("**/#play/2")
        assert page.evaluate("localStorage.getItem('word-kanji:campaign-two:v1')") == saved_two
        assert not errors, errors
        # New browser restores both modes from the same code.
        fresh = context.new_page()
        page.evaluate("localStorage.clear()")
        fresh.goto(url)
        fresh.locator("#save-open").click(); fresh.locator("#save-code").fill(combined)
        fresh.locator("#save-import").click()
        fresh.wait_for_function("localStorage.getItem('word-kanji:campaign-two:v1') !== null")
        assert json.loads(fresh.evaluate("localStorage.getItem('word-kanji:campaign:v1')"))["completed"] == 2
        assert json.loads(fresh.evaluate("localStorage.getItem('word-kanji:campaign-two:v1')"))["completed"] == 1
        browser.close()
    print("Two-cell browser checks passed: input, layout, progress isolation, reveal, legacy and multi-mode saves.")


if __name__ == "__main__":
    main()
