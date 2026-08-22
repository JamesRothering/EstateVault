import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ComposeLedgerTests(unittest.TestCase):
    def test_official_firefly_image_listens_on_8080(self):
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("image: fireflyiii/core", text)
        self.assertIn("8080:8080", text)
        self.assertIn("python3", (ROOT / "README.md").read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/bootstrap_env.py", readme)
        self.assertIn("docker compose up -d", readme)
        self.assertIn("http://127.0.0.1:8080", readme)

    def test_repo_is_not_a_firefly_fork(self):
        self.assertFalse((ROOT / "artisan").exists())
        self.assertFalse((ROOT / "app" / "Http").exists())
        self.assertFalse((ROOT / "composer.json").exists())
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("This repo is not a fork of Firefly", compose)

    def test_bootstrap_env_refuses_to_overwrite(self):
        text = (ROOT / "scripts" / "bootstrap_env.py").read_text(encoding="utf-8")
        self.assertIn("if dest.exists()", text)
        self.assertIn('print(".env already exists")', text)
        self.assertIn("FIREFLY_TOKEN is still empty", text)
