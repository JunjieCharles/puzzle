"""Optional answer-view checks with synthetic data, never real solutions."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_campaign import VERSION, public_record
from test_campaign import sample
from toy import toy
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/puzzle/word-kanji/")
    url = parser.parse_args().url.rstrip("/") + "/"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 320, "height": 568})
        data = {"version": VERSION, "revision": "c" * 16,
                "puzzles": [public_record(sample(i, i, 1)) for i in range(2)]}
        context.route("**/campaign.json", lambda route: route.fulfill(json=data))
        page = context.new_page()
        page.goto(url + "#play/1")
        page.wait_for_function("!document.querySelector('#entry').disabled")
        assert page.locator("#reveal").is_hidden()
        page.evaluate("localStorage.setItem('word-kanji:campaign:v1', JSON.stringify({revision:'cccccccccccccccc',completed:1}))")
        page.reload()
        page.locator("#reveal").wait_for(state="visible")
        stored = page.evaluate("JSON.stringify(localStorage)")
        page.locator("#reveal").click()
        page.wait_for_function("document.querySelector('#entry').value === String.fromCodePoint(0x3400)")
        assert page.locator("#entry").input_value() == toy(0)
        assert page.locator("#entry").evaluate("e => e.readOnly")
        page.wait_for_timeout(1100)
        assert page.url.endswith("#play/1")
        assert page.evaluate("JSON.stringify(localStorage)") == stored
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight")
        assert page.locator("#hide-answer").is_visible()
        assert page.locator("#review-next").is_enabled()
        page.locator("#hide-answer").click()
        assert page.locator("#entry").input_value() == ""
        assert not page.locator("#entry").evaluate("e => e.readOnly")
        assert page.locator("#submit").is_visible()
        assert page.locator("#reveal").is_visible()
        assert page.locator("#review-next").is_hidden()
        page.locator("#reveal").click()
        page.locator("#hide-answer").wait_for(state="visible")
        length = page.evaluate("history.length")
        page.locator("#review-next").click()
        page.wait_for_url("**/#play/2")
        assert page.evaluate("history.length") == length
        assert page.locator("#entry").input_value() == ""
        assert page.locator("#review-next").is_hidden()
        assert page.evaluate("JSON.stringify(localStorage)") == stored
        page.locator("#previous").click()
        page.wait_for_url("**/#play/1")
        page.reload()
        page.locator("#reveal").wait_for(state="visible")
        assert page.locator("#entry").input_value() == ""
        page.locator("#reveal").click()
        page.locator("#play .back").click()
        page.locator("#levels").wait_for(state="visible")
        page.locator(".level-tile").nth(1).click()
        page.wait_for_timeout(1100)
        assert page.locator("#entry").input_value() == ""
        assert page.locator("#reveal").is_hidden()
        page.evaluate("localStorage.setItem('word-kanji:campaign:v1', JSON.stringify({revision:'cccccccccccccccc',completed:2}))")
        page.reload()
        page.locator("#reveal").click()
        page.locator("#hide-answer").wait_for(state="visible")
        assert page.locator("#review-next").is_disabled()
        # Viewing and hiding must not move the board, submit slot or navigation.
        for width, height in [(320,568), (390,844), (844,390), (1920,1080)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#hide-answer").click()
            selectors = [".board", "#entry", ".answer-actions", "#submit", "#previous", "#reveal"]
            before = [page.locator(s).bounding_box() for s in selectors]
            page.locator("#reveal").click()
            page.locator("#hide-answer").wait_for(state="visible")
            for selector, expected in zip(selectors[:-1] + ["#hide-answer"], before):
                actual = page.locator(selector).evaluate("e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}")
                assert all(abs(actual[k] - expected[k]) < 1 for k in expected), (width,height,selector,expected,actual)
            page.locator("#hide-answer").click()
            for selector, expected in zip(selectors, before):
                actual = page.locator(selector).bounding_box()
                assert all(abs(actual[k] - expected[k]) < 1 for k in expected), (width,height,selector)
            page.locator("#reveal").click()
            page.locator("#hide-answer").wait_for(state="visible")
        browser.close()
    print("Reveal checks passed: eligibility, display, no persistence/advance, reload and cancellation.")


if __name__ == "__main__":
    main()
