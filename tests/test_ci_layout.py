import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class CiLayoutTests(unittest.TestCase):
    def test_ci_workflow_runs_unittest(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -v", text)
        self.assertIn("pull_request", text)
        self.assertIn(".env.example", text)

    def test_ready_workflow_does_not_merge(self):
        text = (ROOT / ".github" / "workflows" / "ready.yml").read_text(encoding="utf-8")
        self.assertIn("label.name == 'ready'", text)
        self.assertIn("autoCreatePr", text)
        self.assertNotIn("gh pr merge", text)

    def test_ready_workflow_only_runs_on_issue_labels(self):
        text = (ROOT / ".github" / "workflows" / "ready.yml").read_text(encoding="utf-8")
        self.assertIn("on:\n  issues:", text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotRegex(
            text,
            r"(?m)^on:\n(?:  .*\n)*  push:",
            "ready.yml must not run on push; GitHub emails a failure for every commit",
        )

    def test_ready_workflow_does_not_use_secrets_in_if(self):
        """GitHub rejects secrets in if: and emails a 0s failure named after the file."""
        text = (ROOT / ".github" / "workflows" / "ready.yml").read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("if:") and "secrets." in line:
                self.fail(f"line {i}: do not use secrets in if: ({line.strip()})")
        self.assertIn("CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}", text)
        self.assertIn('mode=missing_key', text)

    def test_review_compose_uses_separate_ports_and_volumes(self):
        text = (ROOT / "docker-compose.review.yml").read_text(encoding="utf-8")
        self.assertIn("8190:8090", text)
        self.assertIn("8180:8080", text)
        self.assertIn("estatevault_review_firefly_iii_db", text)
        self.assertNotIn("8080:8080", text)

    def test_review_estate_uses_stable_firefly(self):
        text = (ROOT / "docker-compose.review-estate.yml").read_text(encoding="utf-8")
        self.assertIn("8190:8090", text)
        self.assertIn("estatevault_firefly", text)
        self.assertIn("external: true", text)
