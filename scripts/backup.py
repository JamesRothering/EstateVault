"""Back up Firefly Docker volumes. Never commit .env. No second ledger."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_VOLUME_KEYS = ("firefly_iii_upload", "firefly_iii_db")
DEFAULT_PROJECT = "estatevault"
DEFAULT_BACKUP_PARENT = Path.home() / "EstateVault-backups"
DEFAULT_ESTATE_DB = ROOT / "data" / "estate.sqlite"


def compose_volume_keys(compose_text: str) -> tuple[str, ...]:
    keys: list[str] = []
    in_volumes = False
    for raw in compose_text.splitlines():
        if raw.startswith("volumes:"):
            in_volumes = True
            continue
        if not in_volumes:
            continue
        if raw and not raw[0].isspace() and not raw.lstrip().startswith("#"):
            break
        stripped = raw.strip()
        if stripped.endswith(":") and not stripped.startswith("#") and " " not in stripped[:-1]:
            keys.append(stripped[:-1])
    return tuple(keys)


def docker_volume_name(project: str, key: str) -> str:
    return f"{project}_{key}"


def default_backup_dir() -> Path:
    override = os.environ.get("ESTATE_BACKUP_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_BACKUP_PARENT


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _archive_argv(volume: str, dest: Path, archive_name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume}:/volume:ro",
        "-v",
        f"{dest}:/backup",
        "alpine:3.20",
        "tar",
        "czf",
        f"/backup/{archive_name}",
        "-C",
        "/volume",
        ".",
    ]


def _manifest(*, volume_keys: tuple[str, ...], project: str, include_env: bool, include_estate_db: bool) -> str:
    lines = [
        "Estate Vault backup",
        "Ledger: official Firefly III volumes only. No second ledger.",
        f"Compose project: {project}",
        "Volumes:",
    ]
    for key in volume_keys:
        lines.append(f"  - {key} -> {docker_volume_name(project, key)}.tar.gz as {key}.tar.gz")
    lines.append("Secrets: .env copied here with mode 600." if include_env else "Secrets: .env not copied.")
    if include_estate_db:
        lines.append("Estate metadata: estate.sqlite copied here with mode 600. Contacts/docs only — not a ledger.")
    else:
        lines.append("Estate metadata: no estate.sqlite yet (US-040).")
    lines.append("FIREFLY_TOKEN stays out of git. Family sessions must not receive it.")
    lines.append("Restore: see docs/BACKUP.md. Copy this folder off this Mac (another disk / Time Machine).")
    return "\n".join(lines) + "\n"


def backup(
    *,
    dest_parent: Path,
    compose_text: str,
    project: str = DEFAULT_PROJECT,
    run=subprocess.run,
    env_path: Path | None = None,
    estate_db: Path | None = None,
    include_env: bool = True,
    dry_run: bool = False,
) -> Path:
    keys = compose_volume_keys(compose_text)
    if keys != COMPOSE_VOLUME_KEYS:
        raise RuntimeError(f"Unexpected Compose volumes {keys!r}; refusing to invent a ledger.")
    dest = dest_parent / _stamp()
    if dry_run:
        return dest
    dest.mkdir(parents=True, exist_ok=False)
    os.chmod(dest, 0o700)
    for key in keys:
        archive = f"{key}.tar.gz"
        argv = _archive_argv(docker_volume_name(project, key), dest, archive)
        run(argv, check=True)
    if include_env:
        source = env_path if env_path is not None else ROOT / ".env"
        if source.is_file():
            target = dest / ".env"
            shutil.copy2(source, target)
            os.chmod(target, 0o600)
    db_source = DEFAULT_ESTATE_DB if estate_db is None else estate_db
    copied_estate_db = False
    if db_source.is_file():
        target_db = dest / "estate.sqlite"
        shutil.copy2(db_source, target_db)
        os.chmod(target_db, 0o600)
        copied_estate_db = True
    (dest / "MANIFEST.txt").write_text(
        _manifest(
            volume_keys=keys,
            project=project,
            include_env=include_env,
            include_estate_db=copied_estate_db,
        ),
        encoding="utf-8",
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back up Firefly Docker volumes. Does not commit .env."
    )
    parser.add_argument(
        "--dest",
        default="",
        help="Backup parent directory (default: $ESTATE_BACKUP_DIR or ~/EstateVault-backups)",
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-env", action="store_true", help="Do not copy .env into the backup folder")
    args = parser.parse_args()
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    parent = Path(args.dest).expanduser() if args.dest else default_backup_dir()
    dest = backup(
        dest_parent=parent,
        compose_text=compose,
        project=args.project,
        include_env=not args.skip_env,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(f"Dry run. Would write {dest}")
        for key in COMPOSE_VOLUME_KEYS:
            print(f"  {key} -> {docker_volume_name(args.project, key)}")
        print("Will not commit .env.")
        return
    print(f"Wrote {dest}")
    print("Copy that folder to another disk. A backup on this Mac does not survive a dead disk.")


if __name__ == "__main__":
    main()
