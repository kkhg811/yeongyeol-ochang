# -*- coding: utf-8 -*-
"""로컬 미리보기: python serve.py  →  http://localhost:8791"""
import os
import argparse
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote

PORT = 8791
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

class PreviewHandler(SimpleHTTPRequestHandler):
    """Serve the existing extensionless Cloudflare routes in local preview too."""
    def send_head(self):
        request = urlsplit(self.path)
        candidate = unquote(request.path).lstrip("/")
        resolved = os.path.realpath(os.path.join(self.directory, candidate))
        inside = os.path.commonpath([os.path.realpath(self.directory), resolved]) == os.path.realpath(self.directory)
        if inside and not os.path.splitext(candidate)[1] and os.path.isfile(resolved + ".html"):
            original = self.path
            self.path = request.path + ".html" + (("?" + request.query) if request.query else "")
            try:
                return super().send_head()
            finally:
                self.path = original
        return super().send_head()

    def end_headers(self):
        if os.path.isfile(os.path.join(self.directory, "review-routes.json")):
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        super().end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", PORT)))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--strictPort", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=SITE)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://localhost:{args.port}/"
    print(f"연결한의원 청주오창 미리보기: {url}  (종료: Ctrl+C)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
