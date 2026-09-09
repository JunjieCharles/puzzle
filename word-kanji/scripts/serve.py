"""Serve only public website files, never repository sources or private datasets."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def public_path(url, root=ROOT):
    """Map the URL prefix to a project's public directory without serving sources."""
    parts = unquote(urlsplit(url).path).strip("/").split("/")
    if len(parts) < 2 or parts[:2] != ["puzzle", root.name]:
        return None
    if any(part in {"", ".", ".."} or "\\" in part or ":" in part for part in parts):
        return None
    public = root / "public"
    if not public.is_dir() or public.resolve() != public.absolute():
        return None
    target = public.joinpath(*parts[2:]).resolve()
    if target != public and public not in target.parents:
        return None
    return target


class PublicHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return str(public_path(path))

    def send_head(self):
        if public_path(self.path) is None:
            self.send_error(404)
            return None
        return super().send_head()

    def list_directory(self, path):
        self.send_error(404)
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"http://localhost:{args.port}/puzzle/{ROOT.name}/", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", args.port), PublicHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
