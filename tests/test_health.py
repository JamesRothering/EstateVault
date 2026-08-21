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

    def test_warning_account_is_named(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Chase Checking", "last_activity": "2026-08-19"},
                },
                {
                    "id": "2",
                    "attributes": {"name": "Amex", "last_activity": "2026-07-27"},
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.WARNING)
        self.assertEqual(report.stale_account, "Amex")
        self.assertEqual(report.blocking, "Amex")
        payload = report_to_dict(report)
        self.assertEqual(payload["stale_account"], "Amex")
        self.assertEqual(payload["accounts"][1]["last_activity"], "2026-07-27")
        self.assertEqual(payload["accounts"][1]["age_days"], 24)
        self.assertEqual(payload["accounts"][1]["status"], "WARNING")

    def test_stale_account_still_named_when_bill_is_worse(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "2",
                    "attributes": {"name": "Amex", "last_activity": "2026-07-27"},
                },
            ],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Electric",
                        "active": True,
                        "pay_dates": ["2026-08-01"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertEqual(report.stale_bill, "Electric")
        self.assertEqual(report.stale_account, "Amex")

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

    def test_unused_account_does_not_block_current(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
                {
                    "id": "2",
                    "attributes": {"name": "Wells Fargo savings account", "last_activity": "2026-08-19"},
                },
                {"id": "3", "attributes": {"name": "Cash wallet"}},
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertIsNone(report.stale_account)
        self.assertIs(report.accounts[2].status, Status.EMPTY)
        self.assertTrue(any("Cash wallet" in note for note in report.notes))

    def test_only_unused_accounts_is_empty(self):
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[{"id": "3", "attributes": {"name": "Cash wallet"}}],
            as_of=date(2026, 8, 20),
        )
        self.assertIs(report.status, Status.EMPTY)
        self.assertEqual(report.stale_account, "Cash wallet")

    def test_no_bills_does_not_block_current_accounts(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertEqual(report.bills, ())

    def test_overdue_unpaid_bill_blocks_current(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Electric",
                        "active": True,
                        "next_expected_match": "2026-08-01T00:00:00+00:00",
                        "pay_dates": ["2026-08-01T00:00:00+00:00"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertEqual(report.stale_bill, "Electric")
        self.assertEqual(report.blocking, "Electric")
        self.assertIs(report.bills[0].status, Status.STALE)
        self.assertTrue(report.bills[0].overdue)
        self.assertTrue(any("Electric" in note for note in report.notes))

    def test_paid_bill_does_not_block_current(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Electric",
                        "active": True,
                        "next_expected_match": "2026-09-01T00:00:00+00:00",
                        "pay_dates": ["2026-08-01T00:00:00+00:00"],
                        "paid_dates": [
                            {
                                "transaction_group_id": "12",
                                "date": "2026-08-03T00:00:00+00:00",
                            }
                        ],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertIsNone(report.stale_bill)
        self.assertIs(report.bills[0].status, Status.CURRENT)
        self.assertFalse(report.bills[0].overdue)

    def test_inactive_overdue_bill_is_ignored(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Old magazine",
                        "active": False,
                        "pay_dates": ["2026-08-01T00:00:00+00:00"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertIsNone(report.stale_bill)
        self.assertEqual(report.bills, ())

    def test_past_next_expected_match_without_pay_dates_is_stale(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "4",
                    "attributes": {
                        "name": "HOA",
                        "active": True,
                        "next_expected_match": "2026-07-15",
                        "pay_dates": [],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertEqual(report.stale_bill, "HOA")

    def test_future_expected_bill_does_not_block(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "2",
                    "attributes": {
                        "name": "Insurance",
                        "active": True,
                        "next_expected_match": "2026-11-01T00:00:00+00:00",
                        "pay_dates": ["2026-11-01T00:00:00+00:00"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.CURRENT)
        self.assertIs(report.bills[0].status, Status.CURRENT)
        self.assertFalse(report.bills[0].overdue)

    def test_overdue_bill_with_only_unused_accounts_is_stale(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[{"id": "3", "attributes": {"name": "Cash wallet"}}],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Electric",
                        "active": True,
                        "pay_dates": ["2026-08-01"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertEqual(report.stale_bill, "Electric")

    def test_report_dict_includes_bills(self):
        as_of = date(2026, 8, 20)
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Wells Fargo", "last_activity": "2026-08-19"},
                },
            ],
            bills=[
                {
                    "id": "9",
                    "attributes": {
                        "name": "Electric",
                        "active": True,
                        "pay_dates": ["2026-08-01"],
                        "paid_dates": [],
                    },
                },
            ],
            as_of=as_of,
        )
        payload = report_to_dict(report)
        self.assertEqual(payload["stale_bill"], "Electric")
        self.assertEqual(payload["blocking"], "Electric")
        self.assertEqual(payload["bills"][0]["name"], "Electric")
        self.assertEqual(payload["bills"][0]["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
