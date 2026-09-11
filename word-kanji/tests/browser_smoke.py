"""Optional browser checks: install Playwright separately, use the system Edge.

Run the public-only server first. Real answer mappings are never loaded here;
successful submissions use a synthetic campaign intercepted only in memory.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.export_campaign import public_record, VERSION
from storage import private_output
from test_campaign import sample
from toy import toy
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/puzzle/word-kanji")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    total = len(json.loads((ROOT / "public" / "campaign.json").read_text(encoding="utf-8"))["puzzles"])
    screenshots = private_output(args.screenshots) if args.screenshots else None
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.locator("#home").wait_for(state="visible")
        assert page.url.split("#")[0].endswith("/word-kanji/")
        assert page.locator("#home button:disabled").count() == 1
        page.locator("#help-open").click()
        assert page.locator("#help-dialog").is_visible()
        page.keyboard.press("Escape")
        assert page.locator("#help-dialog").is_hidden()
        # All normal views fit without clipping or document scrollbars, including
        # small phones and landscape. Keep resizing the same page to exercise
        # recalculation of the level grid, not just the initial layout.
        for width, height in ((2560,1290), (1920,1080), (1280,900), (1280,720), (1024,600),
                              (768,1024), (390,844), (375,667), (320,568), (844,390)):
            page.set_viewport_size({"width": width, "height": height})
            for view in ("home", "types", "levels", "play"):
                page.goto(args.url + "/#" + view)
                if view == "levels":
                    page.locator("#level-grid button").first.wait_for(state="visible")
                if view == "play":
                    page.wait_for_function("!document.querySelector('#entry').disabled")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, height, view, "horizontal overflow")
                assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1"), (width, height, view, "vertical overflow")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(args.url + "/#home")
        if screenshots:
            page.screenshot(path=str(screenshots / "home.png"))
        page.locator('a[href="#types"]').first.click()
        assert page.locator("#types button:disabled").count() == 0
        page.locator("#start").click()
        page.locator("#level-grid button").first.wait_for(state="visible")
        page_size = int(page.locator("#level-grid").get_attribute("data-page-size"))
        assert page.locator("#level-grid button").count() == page_size
        assert page.locator("#level-grid button:disabled").count() == page_size - 3
        page.locator("#page-select").select_option(str((total - 1) // page_size))
        assert page.locator("#level-grid button").count() == (total - 1) % page_size + 1
        assert page.locator("#level-grid button").last.inner_text() == str(total)
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#page-select").select_option("0")
        if screenshots:
            page.screenshot(path=str(screenshots / "levels.png"), full_page=True)
        page.locator("#level-grid button").first.click()
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        assert page.locator("#level-count").inner_text() == f"1 / {total}"
        for side in ("top", "left", "bottom", "right"):
            assert len(page.locator(f"#{side}").inner_text()) == 1
        page.reload()
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        page.set_viewport_size({"width": 1280, "height": 900})
        if screenshots:
            page.screenshot(path=str(screenshots / "desktop.png"))
        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if screenshots:
            page.screenshot(path=str(screenshots / "mobile.png"))
        origin = args.url.split("/puzzle/")[0]
        for forbidden in ("/word-kanji/data/hsk-2025.json", "/word-kanji/datasets/one-standard-hsk-disjoint.sqlite", "/AGENTS.md", "/.git/config"):
            assert context.request.get(origin + forbidden).status == 404
        context.close()

        # Exercise submission, storage, reload, review, completion and replay.
        data = {"version": VERSION, "revision": "b" * 16,
                "puzzles": [public_record(sample(i, i, 1)) for i in range(2)]}
        context = browser.new_context(viewport={"width": 375, "height": 812})
        context.route("**/campaign.json", lambda route: route.fulfill(json=data))
        page = context.new_page()
        page.clock.install()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/#play")
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        # Multi-character edits/pastes keep the first complete Unicode character.
        page.locator("#entry").fill(toy(3, 4, 5))
        assert page.locator("#entry").input_value() == toy(3)
        page.locator("#entry").fill(chr(0x20000) + toy(4))
        assert page.locator("#entry").input_value() == chr(0x20000)
        page.locator("#entry").evaluate("""(entry, value) => {
            entry.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
            entry.value = 'pinyin';
            entry.dispatchEvent(new InputEvent('input', {bubbles:true, isComposing:true}));
        }""", None)
        assert page.locator("#entry").input_value() == "pinyin"
        page.locator("#entry").evaluate("""(entry, value) => {
            entry.value = value;
            entry.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:value}));
        }""", toy(3, 4))
        assert page.locator("#entry").input_value() == toy(3)
        page.locator("#entry").fill("")
        page.locator("#submit").click()
        page.wait_for_function("document.querySelector('#entry').getAttribute('aria-invalid') === 'true'")
        page.locator("#entry").fill(toy(9))
        page.locator("#submit").click()
        page.wait_for_function("document.querySelector('#entry').getAttribute('aria-invalid') === 'true'")
        assert page.locator("#next").is_hidden()
        page.locator("#entry").fill(toy(0))
        page.locator("#submit").click()
        page.locator("#next").wait_for(state="visible")
        assert page.locator("#entry").input_value() == toy(0)
        assert page.locator("#entry").evaluate("entry => entry.readOnly")
        page.locator("#help-open").click()
        page.clock.fast_forward(2000)
        page.wait_for_function("document.querySelector('#level-count').textContent === '2 / 2'")
        assert page.locator("#help-dialog").is_visible()
        assert page.locator("#entry").input_value() == ""
        page.locator("#help-dialog .help-close").click()
        page.clock.fast_forward(2000)
        assert page.locator("#level-count").inner_text() == "2 / 2"
        page.locator("#previous").click()
        page.wait_for_function("document.querySelector('#level-count').textContent === '1 / 2'")
        page.locator("#entry").fill(toy(0))
        page.locator("#submit").click()
        page.locator("#next").wait_for(state="visible")
        saved = page.evaluate("JSON.parse(localStorage.getItem('word-kanji:campaign:v2'))")
        assert saved == {"revision": data["revision"], "completed": 1, "pending": [2]}
        assert page.locator("#level-count").inner_text() == "1 / 2"
        # Navigating away during the success pause must cancel automatic advance.
        page.locator('#play a[href="#levels"]').click()
        page.locator("#levels").wait_for(state="visible")
        page.clock.fast_forward(2000)
        assert page.url.endswith("#levels")
        assert page.locator("#entry").input_value() == ""
        page.goto(args.url + "/#play")
        page.reload()
        page.wait_for_function("document.querySelector('#level-count').textContent === '2 / 2'")
        assert page.locator("#entry").input_value() == ""
        page.locator("#previous").click()
        page.wait_for_function("document.querySelector('#level-count').textContent === '1 / 2'")
        assert page.locator("#level-count").inner_text() == "1 / 2"
        page.reload()
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        assert page.locator("#level-count").inner_text() == "1 / 2"
        page.locator('#play a[href="#levels"]').click()
        page.locator("#level-grid button.passed").wait_for(state="visible")
        assert page.locator("#level-grid button:not(:disabled)").count() == 2
        page.locator("#level-grid button").first.click()
        page.wait_for_function("document.querySelector('#play').hidden === false")
        page.locator('#play a[href="#levels"]').click()
        page.locator("#level-grid button").nth(1).click()
        page.wait_for_function("document.querySelector('#level-count').textContent === '2 / 2'")
        page.locator("#entry").fill(toy(1))
        page.locator("#entry").press("Enter")
        page.locator("#next").wait_for(state="visible")
        page.locator("#complete").wait_for(state="visible")
        page.reload()
        page.locator("#complete-count").wait_for(state="visible")
        assert page.locator("#complete-count").inner_text() == "2 / 2"
        assert page.locator("#replay").count() == 0
        assert page.evaluate("JSON.parse(localStorage.getItem('word-kanji:campaign:v2')).completed") == 2
        # Corrupt progress is ignored rather than crashing or unlocking a level.
        page.evaluate("localStorage.setItem('word-kanji:campaign:v2', '{')")
        page.goto(args.url + "/#play/1")
        page.reload()
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        assert page.locator("#level-count").inner_text() == "1 / 2"
        context.close()

        context = browser.new_context(reduced_motion="reduce")
        # Loading failures can be retried without reloading the page.
        attempts = [0]
        def delayed_data(route):
            attempts[0] += 1
            route.fulfill(status=503) if attempts[0] == 1 else route.fulfill(json=data)
        context.route("**/campaign.json", delayed_data)
        context.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('blocked')}})")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/#play")
        page.locator("#retry").wait_for(state="visible")
        page.locator("#retry").click()
        page.wait_for_function("document.querySelector('#entry').disabled === false")
        page.locator("#entry").fill(toy(0))
        page.locator("#submit").click()
        page.locator("#next").wait_for(state="visible")
        page.wait_for_function("document.querySelector('#level-count').textContent === '2 / 2'")
        assert page.locator("#save-warning").is_visible()
        assert page.locator("#level-count").inner_text() == "2 / 2"
        assert page.locator("#entry").input_value() == ""
        assert page.locator("#entry").evaluate("entry => document.activeElement === entry")
        page.keyboard.insert_text(toy(1))
        assert page.locator("#entry").input_value() == toy(1)
        page.keyboard.press("Enter")
        page.locator("#next").wait_for(state="visible")
        context.close()
        browser.close()
        assert not errors, "Browser raised an uncaught error"
    print("Browser checks passed: public routes, mobile layout, submission, progress, replay, retry, unavailable storage.")


if __name__ == "__main__":
    main()
