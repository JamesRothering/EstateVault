import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.wait_http import http_answered, wait_http


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"UNAVAILABLE"}')

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _Unavailable(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(503)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _serve(handler) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/api/health"


class WaitHttpTests(unittest.TestCase):
    def test_connection_refused_is_not_up(self):
        self.assertFalse(http_answered("http://127.0.0.1:1/api/health", timeout=0.5))

    def test_http_200_counts_as_up(self):
        server, url = _serve(_Ok)
        try:
            self.assertTrue(http_answered(url, timeout=2))
            self.assertTrue(wait_http(url, name="Estate", timeout_sec=5, interval_sec=1))
        finally:
            server.shutdown()
            server.server_close()

    def test_http_503_still_counts_as_answered(self):
        server, url = _serve(_Unavailable)
        try:
            self.assertTrue(http_answered(url, timeout=2))
        finally:
            server.shutdown()
            server.server_close()

    def test_wait_times_out_when_nothing_listens(self):
        self.assertFalse(
            wait_http(
                "http://127.0.0.1:1/api/health",
                name="missing",
                timeout_sec=2,
                interval_sec=1,
            )
        )
