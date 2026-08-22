import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from estate.app import build_report
from estate.firefly import FireflyError, about, asset_accounts, fetch_snapshot, get_json
from estate.health import Status


ROOT = Path(__file__).resolve().parent.parent


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FireflyClientTests(unittest.TestCase):
    def test_env_is_gitignored(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env\n", text)

    def test_empty_token_never_calls_firefly(self):
        with patch.dict(os.environ, {"FIREFLY_TOKEN": ""}, clear=False):
            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(FireflyError) as ctx:
                    get_json("/api/v1/about")
                urlopen.assert_not_called()
            self.assertIn("FIREFLY_TOKEN", str(ctx.exception))
            self.assertIn("Personal Access Token", str(ctx.exception))

    def test_fetch_snapshot_empty_token_is_not_ok(self):
        with patch.dict(os.environ, {"FIREFLY_TOKEN": ""}, clear=False):
            ok, err, accounts, bills, _synced, txs = fetch_snapshot()
        self.assertFalse(ok)
        self.assertIn("FIREFLY_TOKEN", err or "")
        self.assertEqual(accounts, [])
        self.assertEqual(bills, [])
        self.assertEqual(txs, [])

    def test_build_report_empty_token_is_unavailable_not_current(self):
        with patch.dict(os.environ, {"FIREFLY_TOKEN": ""}, clear=False):
            report = build_report()
        self.assertIs(report.status, Status.UNAVAILABLE)
        self.assertIsNot(report.status, Status.CURRENT)

    def test_about_sends_bearer_token(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            return _Resp({"data": {"version": "6.2.0"}})

        env = {"FIREFLY_TOKEN": "pat-test", "FIREFLY_URL": "http://ff.example"}
        with patch.dict(os.environ, env, clear=False):
            with patch("urllib.request.urlopen", fake_urlopen):
                payload = about()
        self.assertEqual(payload["data"]["version"], "6.2.0")
        self.assertEqual(captured["url"], "http://ff.example/api/v1/about")
        self.assertEqual(captured["auth"], "Bearer pat-test")

    def test_asset_accounts_query(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _Resp({"data": [{"id": "1", "attributes": {"name": "Wells Fargo"}}]})

        env = {"FIREFLY_TOKEN": "pat-test", "FIREFLY_URL": "http://ff.example"}
        with patch.dict(os.environ, env, clear=False):
            with patch("urllib.request.urlopen", fake_urlopen):
                rows = asset_accounts()
        self.assertEqual(rows[0]["attributes"]["name"], "Wells Fargo")
        self.assertIn("/api/v1/accounts?type=asset", captured["url"])

    def test_search_transactions_uses_firefly_query(self):
        from estate.firefly import search_transactions

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _Resp(
                {
                    "data": [
                        {
                            "id": "10",
                            "attributes": {
                                "transactions": [
                                    {"date": "2026-06-01", "reconciled": False, "source_id": "1"}
                                ]
                            },
                        }
                    ],
                    "meta": {"pagination": {"current_page": 1, "total_pages": 1}},
                }
            )

        env = {"FIREFLY_TOKEN": "pat-test", "FIREFLY_URL": "http://ff.example"}
        with patch.dict(os.environ, env, clear=False):
            with patch("urllib.request.urlopen", fake_urlopen):
                rows = search_transactions("reconciled:false")
        self.assertEqual(rows[0]["id"], "10")
        self.assertIn("/api/v1/search/transactions?query=", captured["url"])
        self.assertIn("reconciled", captured["url"])
