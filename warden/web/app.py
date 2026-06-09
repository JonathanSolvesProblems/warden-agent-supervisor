"""Stdlib HTTP server for the Warden dashboard.

    python -m warden.web.app        # then open http://127.0.0.1:8080

Routes
    GET  /                 dashboard page
    GET  /health           plain 200 for Cloud Run health probes
    GET  /static/<file>    static assets
    GET  /preview/<file>   evidence assets (Dynatrace screenshots, cover image)
    GET  /events           Server-Sent Events stream of Warden's reasoning
    GET  /api/state        snapshot (fleet, incidents, ledger, pending approval)
    GET  /api/evidence     manifest of which preview assets are available
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
PREVIEW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "preview"))
RUNNER = SimRunner()

_CONTENT_TYPES = {".html": "text/html", ".js": "application/javascript",
                  ".css": "text/css", ".svg": "image/svg+xml",
                  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".webp": "image/webp", ".mp4": "video/mp4"}

EVIDENCE = [
    {
        "id": "spans-list",
        "file": "warden-spans-list-808.png",
        "title": "Live OpenTelemetry spans in Dynatrace",
        "caption": (
            "Distributed Tracing view, filtered to service.name = warden. "
            "Every span here came out of Warden's worker fleet via OTLP/HTTP."
        ),
    },
    {
        "id": "span-detail",
        "file": "warden-span-detail.png",
        "title": "Per-span structured attributes",
        "caption": (
            "service.name = warden, service.namespace = warden.fleet, "
            "agent.id on the span. Exactly the attributes the supervisor reasons over."
        ),
    },
    {
        "id": "metrics-by-agent",
        "file": "warden-metrics-by-agent.png",
        "title": "Per-agent metrics in Dynatrace Notebooks",
        "caption": (
            "warden.agent.actions broken down by agent.id. Three series for "
            "refund-agent, pricing-agent, inventory-agent. Ready for Davis to baseline."
        ),
    },
]


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

    def _evidence_manifest(self) -> dict:
        """Same data as /api/evidence. Factored out so /api/evidence and the
        inlined window.__WARDEN_INITIAL__ stay byte-identical."""
        return {
            "items": [
                {**item, "available": os.path.isfile(os.path.join(PREVIEW_DIR, item["file"]))}
                for item in EVIDENCE
            ]
        }

    def _send_index(self) -> None:
        """Serve index.html with the current Warden snapshot + evidence inlined.

        Without this, a fresh page renders empty panels for the second or two
        between DOMContentLoaded and the first fetch('/api/state'). With it,
        the operator console has live data on the very first paint, and the
        Live Evidence tab paints instantly on tab switch instead of flashing
        blank for the 50-100ms it would otherwise take to fetch /api/evidence.
        """
        path = os.path.join(STATIC_DIR, "index.html")
        with open(path, "rb") as fh:
            html = fh.read()
        # Combine operator state + evidence manifest into one inline payload.
        initial = RUNNER.snapshot()
        initial["evidence"] = self._evidence_manifest()
        snapshot = json.dumps(initial, default=str)
        # Defend against JSON containing '</' which would close the script tag.
        snapshot = snapshot.replace("</", "<\\/")
        payload = f'<script>window.__WARDEN_INITIAL__={snapshot};</script>'.encode("utf-8")
        html = html.replace(b"<!--INITIAL_STATE-->", payload)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html)

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
            self._send_index()
        elif path == "/health":
            self._send_json({"status": "ok", "mode": config.mode()})
        elif path.startswith("/static/"):
            self._send_file(os.path.join(STATIC_DIR, os.path.basename(path)))
        elif path.startswith("/preview/"):
            self._send_file(os.path.join(PREVIEW_DIR, os.path.basename(path)))
        elif path == "/api/state":
            self._send_json(RUNNER.snapshot())
        elif path == "/api/evidence":
            self._send_json(self._evidence_manifest())
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
    # Cloud Run sets PORT and expects the container to bind 0.0.0.0; honor those
    # defaults so the same image runs locally and on Cloud Run with no env tweaks.
    # Treat blank env vars as unset so an empty .env entry does not lock the port.
    host = (os.getenv("WARDEN_WEB_HOST") or "").strip() or "0.0.0.0"
    port_str = (os.getenv("WARDEN_WEB_PORT") or "").strip() or (os.getenv("PORT") or "").strip() or "8080"
    port = int(port_str)
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
