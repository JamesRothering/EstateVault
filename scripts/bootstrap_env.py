#!/usr/bin/env python3
"""Create .env from .env.example with generated secrets. Never overwrites."""

from __future__ import annotations

import secrets
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALPHABET = string.ascii_letters + string.digits


def rand32() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(32))


def main() -> None:
    dest = ROOT / ".env"
    if dest.exists():
        print(".env already exists")
        return
    text = (ROOT / ".env.example").read_text()
    app_key = rand32()
    cron = rand32()
    dbpass = rand32()
    out = []
    for line in text.splitlines():
        if line.startswith("APP_KEY="):
            out.append(f"APP_KEY={app_key}")
        elif line.startswith("STATIC_CRON_TOKEN="):
            out.append(f"STATIC_CRON_TOKEN={cron}")
        elif line.startswith("DB_PASSWORD="):
            out.append(f"DB_PASSWORD={dbpass}")
        elif line.startswith("MYSQL_PASSWORD="):
            out.append(f"MYSQL_PASSWORD={dbpass}")
        else:
            out.append(line)
    dest.write_text("\n".join(out) + "\n")
    print("Wrote .env with generated APP_KEY and DB password. FIREFLY_TOKEN is still empty.")


if __name__ == "__main__":
    main()
