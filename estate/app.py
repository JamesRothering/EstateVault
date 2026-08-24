"""Minimal Estate web UI: health plus estate documents. No Firefly credentials in the page."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from estate.firefly import fetch_snapshot
from estate.health import assess, report_to_dict
from estate.vault import VaultError, add_item, default_db_path, payload as vault_payload

HOST = os.environ.get("ESTATE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ESTATE_PORT", "8090"))
TEMPLATE = Path(__file__).with_name("index.html")


def _ints(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def build_report():
    threshold = _ints("FRESHNESS_THRESHOLD_DAYS", 30)
    ok, error, accounts, bill_rows, synced, transactions = fetch_snapshot(lookback_days=threshold)
    return assess(
        firefly_ok=ok,
        firefly_error=error,
        accounts=accounts,
        bills=bill_rows,
        transactions=transactions,
        threshold_days=threshold,
        warning_lead_days=_ints("WARNING_LEAD_DAYS", 7),
        last_estate_sync=synced,
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"estate {self.address_string()} {format % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            html = TEMPLATE.read_text(encoding="utf-8")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path.startswith("/api/health"):
            try:
                payload = report_to_dict(build_report())
            except Exception as exc:  # noqa: BLE001 — dashboard must still answer
                payload = {
                    "status": "UNAVAILABLE",
                    "firefly_ok": False,
                    "firefly_error": str(exc),
                    "bills": [],
                    "accounts": [],
                    "notes": ["Estate could not finish reading Firefly."],
                }
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
            return
        if path == "/api/vault":
            self._send(200, json.dumps(vault_payload()).encode("utf-8"), "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/vault":
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, b'{"error":"invalid content length"}', "application/json")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, b'{"error":"invalid json"}', "application/json")
            return
        if not isinstance(data, dict):
            self._send(400, b'{"error":"JSON object required"}', "application/json")
            return
        extra = data.get("extra") or {}
        try:
            item = add_item(
                default_db_path(),
                kind=str(data.get("kind") or ""),
                title=str(data.get("title") or ""),
                body=str(data.get("body") or ""),
                extra=extra if isinstance(extra, dict) else {},
            )
        except VaultError as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self._send(400, body, "application/json")
            return
        self._send(201, json.dumps({"item": item.to_dict()}).encode("utf-8"), "application/json")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Estate dashboard http://{HOST}:{PORT}")
    server.serve_forever()
