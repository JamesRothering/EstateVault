import unittest
from datetime import date
from pathlib import Path

from estate.health import Status, assess


ROOT = Path(__file__).resolve().parent.parent


class DeadManHeartbeatTests(unittest.TestCase):
    def test_dashboard_has_no_im_alive_button(self):
        html = (ROOT / "estate" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "estate" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("/webhooks/keepalive", html)
        self.assertNotIn("/webhooks/keepalive", app)
        self.assertNotIn('id="im-alive"', html)
        self.assertNotIn('id="keepalive"', html)
        self.assertNotRegex(html, r"(?i)<button[^>]*>[^<]*alive")
        self.assertIn("Firefly maintenance is the heartbeat", html)
        self.assertIn("US-062", html)

    def test_recent_firefly_activity_is_current_without_a_checkin(self):
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Checking", "last_activity": "2026-08-18"},
                }
            ],
            as_of=date(2026, 8, 18),
            threshold_days=30,
            warning_lead_days=7,
        )
        self.assertIs(report.status, Status.CURRENT)

    def test_stale_activity_is_stale_not_estate_transition(self):
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Checking", "last_activity": "2026-06-01"},
                }
            ],
            as_of=date(2026, 8, 18),
            threshold_days=30,
            warning_lead_days=7,
        )
        self.assertIs(report.status, Status.STALE)
        self.assertNotEqual(report.status.value, "ESTATE TRANSITION")
        self.assertNotIn("ESTATE TRANSITION", {item.value for item in Status})

    def test_warning_is_the_middle_rung_of_the_heartbeat(self):
        report = assess(
            firefly_ok=True,
            firefly_error=None,
            accounts=[
                {
                    "id": "1",
                    "attributes": {"name": "Checking", "last_activity": "2026-07-27"},
                }
            ],
            as_of=date(2026, 8, 20),
            threshold_days=30,
            warning_lead_days=7,
        )
        self.assertIs(report.status, Status.WARNING)
