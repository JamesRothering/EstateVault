import unittest
from datetime import date

from estate.health import Status, assess, classify_age, report_to_dict


class HealthTests(unittest.TestCase):
    def test_unreconciled_firefly_is_never_current(self):
        report = assess(firefly_ok=False, firefly_error="down", accounts=[])
        self.assertIs(report.status, Status.UNAVAILABLE)
        self.assertIsNot(report.status, Status.CURRENT)

    def test_no_accounts_is_empty_not_current(self):
        report = assess(firefly_ok=True, firefly_error=None, accounts=[])
        self.assertIs(report.status, Status.EMPTY)

    def test_stale_account_blocks_overall_current(self):
        as_of = date(2026, 8, 18)
        accounts = [
            {
                "id": "1",
                "attributes": {"name": "Chase Checking", "last_activity": "2026-08-17"},
            },
            {
                "id": "2",
                "attributes": {"name": "Amex", "last_activity": "2026-07-12"},
            },
        ]
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=accounts,
            as_of=as_of,
            threshold_days=30,
            warning_lead_days=7,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertEqual(report.stale_account, "Amex")
        self.assertEqual(report.accounts[1].age_days, 37)

    def test_warning_before_stale(self):
        self.assertIs(classify_age(24, 30, 7), Status.WARNING)
        self.assertIs(classify_age(10, 30, 7), Status.CURRENT)
        self.assertIs(classify_age(31, 30, 7), Status.STALE)

    def test_all_current(self):
        as_of = date(2026, 8, 18)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Chase Checking", "last_activity": "2026-08-17"},
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertIsNone(report.stale_account)
        self.assertEqual(report_to_dict(report)["status"], "CURRENT")


if __name__ == "__main__":
    unittest.main()
