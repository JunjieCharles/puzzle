"""Optional browser history regression checks using only synthetic puzzles."""
import sys
import argparse
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
    data = {"version": VERSION, "revision": "c" * 16,
            "puzzles": [public_record(sample(i, i, 1)) for i in range(2)]}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.route("**/campaign.json", lambda route: route.fulfill(json=data))
        page = context.new_page()
        page.goto(url)
        page.locator('#home a[href="#types"]').click()
        page.locator("#start").click()
        page.locator(".level-tile").first.click()
        length = page.evaluate("history.length")
        page.locator("#entry").fill(toy(0))
        page.locator("#submit").click()
        page.wait_for_url("**/#play/2")
        assert page.evaluate("history.length") == length
        page.locator("#previous").click()
        page.wait_for_url("**/#play/1")
        assert page.evaluate("history.length") == length
        page.go_back()
        page.wait_for_url("**/#levels")
        page.go_forward()
        page.wait_for_url("**/#play/1")
        page.reload()
        page.locator("#play .back").click()
        page.wait_for_url("**/#levels")
        page.go_back()
        page.wait_for_url("**/#types")
        page.go_back()
        page.locator("#home").wait_for(state="visible")
        # Re-enter, finish the last synthetic puzzle, then leave the completion screen.
        page.locator('#home a[href="#types"]').click()
        page.locator("#start").click()
        page.locator(".level-tile").nth(1).click()
        page.locator("#entry").fill(toy(1))
        page.locator("#submit").click()
        page.wait_for_url("**/#complete")
        page.go_back()
        page.wait_for_url("**/#levels")
        page.locator(".level-tile").first.click()
        page.locator("#entry").fill(toy(0))
        page.locator("#submit").click()
        page.locator("#next").wait_for(state="visible")
        page.go_back()
        page.wait_for_url("**/#levels")
        page.wait_for_timeout(1100)
        assert page.url.endswith("#levels")
        # Direct links do not fabricate parent history; visible navigation still works.
        direct = context.new_page()
        direct.goto(url + "#play/1")
        direct.locator("#play .back").click()
        direct.wait_for_url("**/#levels")
        direct.locator("#levels .back").click()
        direct.wait_for_url("**/#types")
        browser.close()
    print("Navigation checks passed: auto advance, previous, back/forward, reload, completion, cancellation, direct links.")


if __name__ == "__main__":
    main()
