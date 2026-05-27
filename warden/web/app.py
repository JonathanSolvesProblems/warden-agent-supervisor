"""Stdlib HTTP server for the Warden dashboard.

    python -m warden.web.app        # then open http://127.0.0.1:8080

Routes
    GET  /                 dashboard page
    GET  /static/<file>    static assets
    GET  /events           Server-Sent Events stream of Warden's reasoning
    GET  /api/state        snapshot (fleet, incidents, ledger, pending approval)
    POST /api/inject       {"scenario": "..."} inject a rogue scenario
    POST /api/decision     {"approved": true|false} answer a human-in-the-loop gate
    POST /api/reset        rebuild a fresh fleet
"""

from __future__ import annotations

import json
import os
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config
from .runner import SimRunner

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
RUNNER = SimRunner()

_CONTENT_TYPES = {".html": "text/html", ".js": "application/javascript",
                  ".css": "text/css", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # quiet the default request logging
        return

    # --- helpers -------------------------------------------------------------
    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self._send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(path)[1]
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    # --- routing -------------------------------------------------------------
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"))
        elif path.startswith("/static/"):
            self._send_file(os.path.join(STATIC_DIR, os.path.basename(path)))
        elif path == "/api/state":
            self._send_json(RUNNER.snapshot())
        elif path == "/events":
            self._stream_events()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path == "/api/inject":
            self._send_json(RUNNER.inject(self._read_json().get("scenario", "")))
        elif self.path == "/api/decision":
            self._send_json(RUNNER.decide(bool(self._read_json().get("approved", False))))
        elif self.path == "/api/reset":
            RUNNER.reset()
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)

    # --- SSE -----------------------------------------------------------------
    def _stream_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.close_connection = True  # SSE is a long-lived, non-reusable stream
        q = RUNNER.subscribe()
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(RUNNER.sse(msg))
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")  # comment frame to hold the connection
                self.wfile.flush()
        except Exception:
            pass  # client went away; benign
        finally:
            RUNNER.unsubscribe(q)


class QuietServer(ThreadingHTTPServer):
    """Swallow benign client-disconnect errors instead of dumping tracebacks."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, OSError)):
            return  # client closed the tab / stream; nothing to see here
        super().handle_error(request, client_address)


def main() -> None:
    host = os.getenv("WARDEN_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WARDEN_WEB_PORT", "8080"))
    RUNNER.start()
    print(f"Warden dashboard [mode: {config.mode()}] -> http://{host}:{port}")
    server = QuietServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
