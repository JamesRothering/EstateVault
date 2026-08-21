import unittest
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parent.parent / "estate" / "index.html"


class DashboardTests(unittest.TestCase):
    def test_banner_names_the_account_to_reconcile(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("Account to reconcile:", html)
        self.assertIn("data.stale_account", html)
        self.assertIn("stale-account", html)
