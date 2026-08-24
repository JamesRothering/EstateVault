import json
import os
import sqlite3
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from estate.vault import (
    KINDS,
    VaultError,
    add_item,
    default_db_path,
    grouped_items,
    list_items,
)


ROOT = Path(__file__).resolve().parent.parent


class VaultStoreTests(unittest.TestCase):
    def test_kinds_match_the_story(self):
        self.assertEqual(
            KINDS,
            ("contact", "document", "instruction", "insurance", "property", "vehicle"),
        )

    def test_default_db_is_gitignored_data_not_a_ledger_volume(self):
        path = default_db_path()
        self.assertEqual(path.name, "estate.sqlite")
        self.assertEqual(path.parent.name, "data")
        self.assertTrue(str(path).startswith(str(ROOT)))
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/\n", gitignore)
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("estate.sqlite", compose)
        self.assertIn("fireflyiii/core", compose)

    def test_add_and_list_contact(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            item = add_item(
                path,
                kind="contact",
                title="Estate attorney",
                body="Call first if James is unreachable.",
                extra={"phone": "555-0100", "email": "lawyer@example.com"},
            )
            self.assertEqual(item.kind, "contact")
            self.assertEqual(item.title, "Estate attorney")
            self.assertIn("unreachable", item.body)
            rows = list_items(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].extra["phone"], "555-0100")
            self.assertEqual(rows[0].id, item.id)

    def test_stores_every_story_kind(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            for kind in KINDS:
                add_item(path, kind=kind, title=f"{kind} title", body=f"{kind} body")
            grouped = grouped_items(path)
            self.assertEqual(tuple(grouped.keys()), KINDS)
            for kind in KINDS:
                self.assertEqual(len(grouped[kind]), 1)
                self.assertEqual(grouped[kind][0].title, f"{kind} title")

    def test_rejects_transaction_kind(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            with self.assertRaises(VaultError):
                add_item(path, kind="transaction", title="payee", body="100.00")
            with self.assertRaises(VaultError):
                add_item(path, kind="bill", title="rent", body="")
            self.assertEqual(list_items(path), [])

    def test_schema_has_no_transactions_table(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            add_item(path, kind="instruction", title="Who to call", body="Attorney, then sister.")
            with sqlite3.connect(path) as conn:
                names = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertIn("items", names)
            self.assertNotIn("transactions", names)
            self.assertNotIn("accounts", names)
            self.assertNotIn("bills", names)

    def test_missing_file_lists_empty(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(list_items(Path(tmp) / "missing.sqlite"), [])
            self.assertEqual(grouped_items(Path(tmp) / "missing.sqlite")["contact"], [])

    def test_does_not_copy_firefly_token_into_sqlite(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            with patch.dict(os.environ, {"FIREFLY_TOKEN": "secret-pat-must-not-land"}):
                add_item(
                    path,
                    kind="document",
                    title="Will location",
                    body="Safe deposit box 12.",
                )
            raw = path.read_bytes()
            self.assertNotIn(b"secret-pat-must-not-land", raw)
            self.assertNotIn(b"FIREFLY_TOKEN", raw)

    def test_blank_title_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "estate.sqlite"
            with self.assertRaises(VaultError):
                add_item(path, kind="contact", title="  ", body="x")


class VaultHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Path(self.tmp.name) / "estate.sqlite"
        self.env = patch.dict(os.environ, {"ESTATE_DB": str(self.db)})
        self.env.start()
        from estate.app import Handler
        from http.server import ThreadingHTTPServer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.env.stop()
        self.tmp.cleanup()

    def _request(self, method: str, path: str, body: dict | None = None):
        conn = HTTPConnection(self.host, self.port, timeout=5)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(payload))
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        data = json.loads(raw.decode("utf-8")) if raw else None
        return response.status, data

    def test_get_vault_empty(self):
        status, data = self._request("GET", "/api/vault")
        self.assertEqual(status, 200)
        self.assertEqual(data["ledger"], "firefly")
        self.assertFalse(data["is_ledger"])
        self.assertEqual(data["items"], [])
        for kind in KINDS:
            self.assertIn(kind, data["by_kind"])
            self.assertEqual(data["by_kind"][kind], [])

    def test_post_and_get_contact(self):
        status, created = self._request(
            "POST",
            "/api/vault",
            {
                "kind": "insurance",
                "title": "Term life",
                "body": "Policy in the filing cabinet.",
                "extra": {"carrier": "Example Life"},
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["item"]["kind"], "insurance")
        self.assertEqual(created["item"]["extra"]["carrier"], "Example Life")
        status, data = self._request("GET", "/api/vault")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["by_kind"]["insurance"][0]["title"], "Term life")

    def test_post_transaction_kind_is_rejected(self):
        status, data = self._request(
            "POST",
            "/api/vault",
            {"kind": "transaction", "title": "Grocery", "body": "42.00"},
        )
        self.assertEqual(status, 400)
        self.assertIn("not a ledger", data["error"].lower())
        status, listed = self._request("GET", "/api/vault")
        self.assertEqual(listed["items"], [])


class VaultDashboardTests(unittest.TestCase):
    def test_dashboard_has_vault_section_not_a_ledger(self):
        html = (ROOT / "estate" / "index.html").read_text(encoding="utf-8")
        self.assertIn("/api/vault", html)
        self.assertIn("Estate documents", html)
        self.assertIn("contact", html)
        self.assertIn("document", html)
        self.assertIn("instruction", html)
        self.assertIn("insurance", html)
        self.assertIn("property", html)
        self.assertIn("vehicle", html)
        self.assertIn("Firefly must not hold", html)
        self.assertNotIn("FIREFLY_TOKEN", html)
        self.assertIn('fetch("/api/health")', html)


if __name__ == "__main__":
    unittest.main()
