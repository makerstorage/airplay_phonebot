"""Serves the calibration page to Safari on the iPhone: the page reports every touch and draws
the "view" (targets, title) the calibration sets."""

import hashlib
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_RAW = (Path(__file__).parent / "page.html").read_bytes()
BUILD = hashlib.md5(_RAW).hexdigest()[:8]       # the page reloads itself when the Mac serves a newer one
PAGE = _RAW.replace(b"__BUILD__", BUILD.encode())


class _Handler(BaseHTTPRequestHandler):
    touches: list[tuple[float, float]] = []  # every touch the page saw, in page (CSS) pixels
    view: dict = {}                          # what the page draws: {"round", "title", "targets": [...], ...}
    page: dict = {}                          # the page's last call: {"w", "h", "t"} (viewport in page pixels)

    def _view(self) -> bytes:
        return json.dumps({**_Handler.view, "build": BUILD}).encode()

    def _reply(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/view"):  # the page calls in twice a second with its size
            q = parse_qs(urlparse(self.path).query)
            if "w" in q and "h" in q:
                _Handler.page = {"w": float(q["w"][0]), "h": float(q["h"][0]), "t": time.time()}
            self._reply(self._view(), "application/json")
        else:
            self._reply(PAGE, "text/html; charset=utf-8")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            t = json.loads(body)
            _Handler.touches.append((float(t["x"]), float(t["y"])))
        except (ValueError, KeyError, TypeError):
            pass
        self._reply(self._view(), "application/json")

    def log_message(self, *args):
        pass


def local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]


def start_server(port: int) -> tuple[ThreadingHTTPServer, str]:
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{local_ip()}:{port}"


def touch_points() -> list[tuple[float, float]]:
    """Every touch the calibration page has seen, in page pixels (oldest first)."""
    return _Handler.touches


def page_info(max_age_s: float = 3.0) -> dict | None:
    """The viewport of the calibration page ({"w", "h"} in page pixels), or None if the page has not
    called in lately (not open, phone asleep, another tab in front)."""
    p = _Handler.page
    return p if p and time.time() - p["t"] <= max_age_s else None


def set_view(view: dict) -> None:
    """What the calibration page draws from now on."""
    _Handler.view = view
