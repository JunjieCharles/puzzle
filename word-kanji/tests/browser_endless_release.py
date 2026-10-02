"""Exercise the built static release and real vocabulary without logging answers."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
from threading import Thread
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_site import build_site


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".json": "application/json"}
    def log_message(self, *_):
        pass


def main():
    with tempfile.TemporaryDirectory() as folder:
        build_site(folder)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=folder))
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844}); errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("response", lambda r: errors.append(f"HTTP {r.status}") if r.status >= 400 else None)
                base = f"http://127.0.0.1:{server.server_port}/puzzle/word-kanji"
                page.goto(base + "#endless-one")
                page.wait_for_function("!document.querySelector('#entry').disabled")
                assert page.url == base + "/#endless-one"
                for mode in ("one", "two"):
                    page.evaluate("mode => localStorage.setItem(`word-kanji:endless-${mode}-standard:v1`, JSON.stringify({revision:'endless-v1',next:10000}))", mode)
                    start = time.perf_counter()
                    page.goto(base + "/#endless-" + mode)
                    page.reload()
                    page.wait_for_function("document.querySelector('#level-title').textContent.includes('10000') && !document.querySelector('#entry').disabled", timeout=60000)
                    duration = round((time.perf_counter() - start) * 1000)
                    clues = page.locator("#board .clue").all_text_contents()
                    page.reload()
                    page.wait_for_function("!document.querySelector('#entry').disabled", timeout=60000)
                    assert page.locator("#board .clue").all_text_contents() == clues
                    assert page.locator("#entry").input_value() == ""
                    print(f"Built release: {mode}, level 10000, restore {duration} ms, reload matched")
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    main()
