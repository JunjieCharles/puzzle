import importlib.util
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location('floorplan_serve', Path(__file__).resolve().parents[1]/'scripts/serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class PublicServerTests(unittest.TestCase):
    def test_public_paths_refresh_assets_and_source_isolation(self):
        server = serve.ThreadingHTTPServer(('127.0.0.1', 0), serve.PublicHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for suffix in ('', '/', '/index.html', '/style.css', '/app.js', '/analysis.mjs', '/floorplan.mjs', '/placement.mjs', '/fonts/LICENSE.txt', '/fonts/SourceHanSansSC-ExtraLight.otf'):
                with urlopen(base+'/puzzle/hanzi-floorplan'+suffix) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())
                    if suffix.endswith(('.js', '.mjs')):
                        self.assertIn('javascript', response.headers['Content-Type'])
            for suffix in ('/', '/puzzle/hanzi-floorplan/scripts/generate.py', '/puzzle/hanzi-floorplan/%2e%2e/README.md', '/puzzle/hanzi-floorplan/fonts/'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base+suffix)
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
