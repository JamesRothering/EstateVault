import os
import unittest
from pathlib import Path
from unittest.mock import patch

from estate.app import build_report
from estate.health import assess


ROOT = Path(__file__).resolve().parent.parent
_EMPTY_SNAPSHOT = (True, None, [], [], "sync")


class FreshnessWindowTests(unittest.TestCase):
    def test_assess_defaults_to_30_day_window(self):
        report = assess(firefly_ok=True, firefly_error=None, accounts=[])
        self.assertEqual(report.threshold_days, 30)
        self.assertEqual(report.warning_lead_days, 7)

    def test_env_overrides_threshold(self):
        with patch("estate.app.fetch_snapshot", return_value=_EMPTY_SNAPSHOT):
            with patch.dict(
                os.environ,
                {"FRESHNESS_THRESHOLD_DAYS": "45", "WARNING_LEAD_DAYS": "10"},
                clear=False,
            ):
                report = build_report()
        self.assertEqual(report.threshold_days, 45)
        self.assertEqual(report.warning_lead_days, 10)

    def test_blank_env_keeps_30_day_default(self):
        with patch("estate.app.fetch_snapshot", return_value=_EMPTY_SNAPSHOT):
            with patch.dict(
                os.environ,
                {"FRESHNESS_THRESHOLD_DAYS": "", "WARNING_LEAD_DAYS": ""},
                clear=False,
            ):
                report = build_report()
        self.assertEqual(report.threshold_days, 30)
        self.assertEqual(report.warning_lead_days, 7)

    def test_example_env_and_compose_default_to_30(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("FRESHNESS_THRESHOLD_DAYS=30", example)
        self.assertIn("FRESHNESS_THRESHOLD_DAYS: ${FRESHNESS_THRESHOLD_DAYS:-30}", compose)
