"""Serves the calibration page to Safari on the iPhone."""

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = (Path(__file__).parent / "page.html").read_bytes()


class _Handler(BaseHTTPRequestHandler):
    touches: list[bytes] = []

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self):
        # Each tap the page sees is logged; useful to confirm the stylus registers
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        _Handler.touches.append(body)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]


def start_server(port: int) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{local_ip()}:{port}"


def touch_count() -> int:
    return len(_Handler.touches)
