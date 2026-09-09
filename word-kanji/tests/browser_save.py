"""Optional Playwright checks for portable saves, using synthetic progress only."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_campaign import VERSION, public_record
from test_campaign import sample
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/puzzle/word-kanji/")
    args = parser.parse_args()
    url = args.url.rstrip("/") + "/"
    data = {"version": VERSION, "revision": "c" * 16,
            "puzzles": [public_record(sample(i, i, 1)) for i in range(3)]}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        source = browser.new_context(viewport={"width": 320, "height": 568})
        source.route("**/campaign.json", lambda route: route.fulfill(json=data))
        source.add_init_script("""navigator.clipboard.writeText = async () => { throw Error('blocked'); };
            localStorage.setItem('word-kanji:campaign:v1', JSON.stringify({revision:'cccccccccccccccc',completed:2}));""")
        page = source.new_page()
        page.goto(url)
        page.locator("#save-open").click()
        page.locator("#save-export").click()
        page.wait_for_function("document.querySelector('#save-code').value.startsWith('HT101-1.')")
        code = page.locator("#save-code").input_value()
        assert page.locator("#save-code").evaluate("e => e.selectionEnd === e.value.length")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#save-export").click()
        page.wait_for_function("old => document.querySelector('#save-code').value !== old", arg=code)
        second = page.locator("#save-code").input_value()
        assert second != code
        result = page.evaluate("""async code => {
            const {decodeSave, validateModes} = await import('./save-code.js');
            const value = await decodeSave(code);
            if (Object.keys(value).length !== 1 || value['campaign-one-standard'].completed !== 2) throw Error('roundtrip');
            if (Object.keys(validateModes({})).length) throw Error('missing modes');
            if (Object.keys(validateModes({'future-mode':{completed:9}})).length) throw Error('unknown modes');
            for (const completed of [-1, 1.5, '2', null, 1000001]) {
                let rejected = false;
                try { validateModes({'campaign-one-standard':{revision:'cccccccccccccccc',completed}}); }
                catch { rejected = true; }
                if (!rejected) throw Error('invalid progress accepted');
            }
            return true;
        }""", code)
        assert result
        target = browser.new_context(viewport={"width": 390, "height": 844})
        target.route("**/campaign.json", lambda route: route.fulfill(json=data))
        other = target.new_page()
        other.goto(url)
        other.locator("#save-open").click()
        other.locator("#save-code").fill(" \n" + code[:80] + "\n" + code[80:] + " ")
        other.locator("#save-import").click()
        other.wait_for_function("document.querySelector('#levels-count').textContent === '2 / 3'")
        saved = other.evaluate("localStorage.getItem('word-kanji:campaign:v1')")
        assert other.locator("#save-dialog").is_visible()
        # Invalid or incompatible codes must leave the stored progress intact.
        invalid = [code[:-1] + ("0" if code[-1] != "0" else "1"), code.replace("HT101-1", "HT101-2")]
        for revision, completed in [("d" * 16, 1), ("c" * 16, 4)]:
            invalid.append(other.evaluate("""async r => (await import('./save-code.js')).encodeSave({
                'campaign-one-standard':{revision:r[0],completed:r[1]}})""", [revision, completed]))
        for bad in invalid:
            other.locator("#save-code").fill(bad)
            other.locator("#save-import").click()
            other.wait_for_function("!document.querySelector('#save-import').disabled")
            assert other.evaluate("localStorage.getItem('word-kanji:campaign:v1')") == saved
        lower = other.evaluate("""async () => (await import('./save-code.js')).encodeSave({
            'campaign-one-standard':{revision:'cccccccccccccccc',completed:1}})""")
        other.locator("#save-code").fill(lower)
        other.locator("#save-import").click()
        other.wait_for_function("!document.querySelector('#save-import').disabled")
        assert other.evaluate("localStorage.getItem('word-kanji:campaign:v1')") == saved
        other.reload()
        other.wait_for_function("document.querySelector('#levels-count').textContent === '2 / 3'")
        # A blocked storage API still permits import/export in the current session.
        blocked = browser.new_context()
        blocked.route("**/campaign.json", lambda route: route.fulfill(json=data))
        blocked.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw Error('blocked')}})")
        third = blocked.new_page()
        third.goto(url)
        third.locator("#save-open").click()
        third.locator("#save-code").fill(code)
        third.locator("#save-import").click()
        third.wait_for_function("document.querySelector('#levels-count').textContent === '2 / 3'")
        assert third.locator("#save-status").inner_text()
        third.locator("#save-export").click()
        third.wait_for_function("old => document.querySelector('#save-code').value !== old", arg=code)
        browser.close()
    print("Save checks passed: random codes, cross-browser import, legacy progress, validation, no regression, unavailable storage.")


if __name__ == "__main__":
    main()
