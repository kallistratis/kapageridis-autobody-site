"""Local dev server: the browser must re-check every file on each load (no-cache),
so a refresh always shows the latest files, but within one page load a file that
was already fetched (e.g. a preloaded font) is reused instead of downloaded twice."""
import functools
import http.server
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
# Always serve the project folder (the parent of .claude/), whatever the current directory is
SITE_ROOT = Path(__file__).resolve().parent.parent


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        # Like the real host will: unknown addresses get our 404.html (status stays 404)
        page = SITE_ROOT / "404.html"
        if code == 404 and page.exists():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=str(SITE_ROOT))
    print(f"Serving {SITE_ROOT} at http://localhost:{PORT}", flush=True)
    http.server.ThreadingHTTPServer(("", PORT), handler).serve_forever()
