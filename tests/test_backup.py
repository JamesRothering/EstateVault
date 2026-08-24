import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.backup import (
    COMPOSE_VOLUME_KEYS,
    backup,
    compose_volume_keys,
    default_backup_dir,
    docker_volume_name,
)


ROOT = Path(__file__).resolve().parent.parent


class BackupAndSecretsTests(unittest.TestCase):
    def test_compose_names_firefly_volumes_not_a_second_ledger(self):
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        keys = compose_volume_keys(text)
        self.assertEqual(keys, COMPOSE_VOLUME_KEYS)
        self.assertIn("firefly_iii_db", keys)
        self.assertIn("firefly_iii_upload", keys)
        self.assertNotIn("estate_ledger", keys)
        self.assertNotIn("estate_sqlite", keys)

    def test_docker_volume_name_uses_compose_project(self):
        self.assertEqual(
            docker_volume_name("estatevault", "firefly_iii_db"),
            "estatevault_firefly_iii_db",
        )

    def test_default_backup_dir_is_outside_the_repo(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ESTATE_BACKUP_DIR", None)
            dest = default_backup_dir()
        self.assertEqual(dest, Path.home() / "EstateVault-backups")
        repo = ROOT.resolve()
        self.assertFalse(dest.resolve().is_relative_to(repo))

    def test_env_override_sets_backup_dir(self):
        with patch.dict(os.environ, {"ESTATE_BACKUP_DIR": "/Volumes/Offsite/estate"}, clear=False):
            self.assertEqual(default_backup_dir(), Path("/Volumes/Offsite/estate"))

    def test_dry_run_does_not_invoke_docker(self):
        calls: list[list[str]] = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))

        with TemporaryDirectory() as tmp:
            dest = backup(
                dest_parent=Path(tmp),
                compose_text=(ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
                project="estatevault",
                run=fake_run,
                env_path=ROOT / ".env",
                include_env=True,
                dry_run=True,
            )
        self.assertEqual(calls, [])
        self.assertFalse(dest.exists())

    def test_backup_archives_firefly_volumes_and_copies_env_outside_git(self):
        calls: list[list[str]] = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return None

        with TemporaryDirectory() as tmp:
            parent = Path(tmp) / "offsite"
            env_path = Path(tmp) / ".env"
            env_path.write_text("FIREFLY_TOKEN=secret-pat\n", encoding="utf-8")
            dest = backup(
                dest_parent=parent,
                compose_text=(ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
                project="estatevault",
                run=fake_run,
                env_path=env_path,
                estate_db=Path(tmp) / "missing.sqlite",
                include_env=True,
                dry_run=False,
            )
            self.assertTrue(dest.is_dir())
            self.assertTrue((dest / "MANIFEST.txt").is_file())
            manifest = (dest / "MANIFEST.txt").read_text(encoding="utf-8")
            self.assertIn("firefly_iii_db", manifest)
            self.assertIn("firefly_iii_upload", manifest)
            self.assertIn("restore", manifest.lower())
            copied = dest / ".env"
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
            self.assertIn("FIREFLY_TOKEN=secret-pat", copied.read_text(encoding="utf-8"))
            repo = ROOT.resolve()
            self.assertFalse(dest.resolve().is_relative_to(repo))
            self.assertFalse((dest / "estate.sqlite").exists())

        db_call = next(c for c in calls if "firefly_iii_db.tar.gz" in " ".join(c))
        self.assertIn("docker", db_call)
        self.assertIn("estatevault_firefly_iii_db:/volume:ro", " ".join(db_call))
        self.assertTrue(any("firefly_iii_upload.tar.gz" in " ".join(c) for c in calls))
        self.assertEqual(len(calls), 2)

    def test_backup_copies_estate_sqlite_when_present(self):
        calls: list[list[str]] = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return None

        with TemporaryDirectory() as tmp:
            parent = Path(tmp) / "offsite"
            sqlite = Path(tmp) / "estate.sqlite"
            sqlite.write_bytes(b"SQLite format 3\x00not-a-ledger")
            dest = backup(
                dest_parent=parent,
                compose_text=(ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
                project="estatevault",
                run=fake_run,
                env_path=Path(tmp) / "missing.env",
                estate_db=sqlite,
                include_env=True,
                dry_run=False,
            )
            copied = dest / "estate.sqlite"
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
            self.assertEqual(copied.read_bytes(), sqlite.read_bytes())
            manifest = (dest / "MANIFEST.txt").read_text(encoding="utf-8")
            self.assertIn("estate.sqlite", manifest)
            self.assertIn("not a ledger", manifest.lower())
        self.assertEqual(len(calls), 2)

    def test_gitignore_keeps_env_and_local_backups_out_of_git(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env\n", text)
        self.assertIn("backups/\n", text)
        self.assertIn("data/\n", text)

    def test_env_example_has_empty_firefly_token(self):
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        token_lines = [line for line in lines if line.startswith("FIREFLY_TOKEN=")]
        self.assertEqual(token_lines, ["FIREFLY_TOKEN="])

    def test_dashboard_never_embeds_firefly_token(self):
        html = (ROOT / "estate" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "estate" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("FIREFLY_TOKEN", html)
        self.assertNotIn("firefly_token", html.lower())
        self.assertIn("No Firefly credentials in the page", app)

    def test_readme_and_backup_doc_explain_off_mac_copy(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "BACKUP.md").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/backup.py", readme)
        self.assertIn("docs/BACKUP.md", readme)
        self.assertIn("FIREFLY_TOKEN", docs)
        self.assertIn("restore", docs.lower())
        self.assertIn("another disk", docs.lower() + readme.lower())


if __name__ == "__main__":
    unittest.main()
