import unittest
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parent.parent / "estate" / "index.html"


class DashboardTests(unittest.TestCase):
    def test_banner_names_the_account_to_reconcile(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("Account to reconcile:", html)
        self.assertIn("data.stale_account", html)
        self.assertIn("stale-account", html)

    def test_dashboard_loads_health_from_firefly_api(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('fetch("/api/health")', html)
        self.assertIn("data.status", html)
        self.assertIn("data.accounts", html)
        for status in ("CURRENT", "WARNING", "STALE", "EMPTY", "UNAVAILABLE"):
            self.assertIn(status, html)
        self.assertIn("Reconciled through", html)
        self.assertIn("statement_date", html)
        self.assertIn("imported_date", html)
        self.assertIn("reconciled_through", html)
        self.assertIn("Oldest unreconciled", html)
        self.assertIn("oldest_unreconciled", html)
        self.assertIn("Last Firefly import/sync", html)
        self.assertIn("last_import_at", html)
        self.assertIn("Pay from", html)
        self.assertIn("b.frequency", html)
        self.assertIn("b.pay_from", html)
