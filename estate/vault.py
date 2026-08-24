"""Estate metadata store. Contacts and documents only — not a Firefly ledger."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KINDS = (
    "contact",
    "document",
    "instruction",
    "insurance",
    "property",
    "vehicle",
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "estate.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (
        kind IN ('contact','document','instruction','insurance','property','vehicle')
    ),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    extra TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class VaultError(ValueError):
    pass


@dataclass(frozen=True)
class VaultItem:
    id: int
    kind: str
    title: str
    body: str
    extra: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "extra": self.extra,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def default_db_path() -> Path:
    override = os.environ.get("ESTATE_DB", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(row: sqlite3.Row) -> VaultItem:
    extra_raw = row["extra"] or "{}"
    try:
        extra = json.loads(extra_raw)
    except json.JSONDecodeError:
        extra = {}
    if not isinstance(extra, dict):
        extra = {}
    return VaultItem(
        id=int(row["id"]),
        kind=row["kind"],
        title=row["title"],
        body=row["body"] or "",
        extra=extra,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def add_item(
    path: Path,
    *,
    kind: str,
    title: str,
    body: str = "",
    extra: dict[str, Any] | None = None,
) -> VaultItem:
    kind = (kind or "").strip().lower()
    title = (title or "").strip()
    body = body or ""
    extra = extra or {}
    if kind not in KINDS:
        raise VaultError("Unknown kind; Estate vault is not a ledger.")
    if not title:
        raise VaultError("Title is required.")
    if not isinstance(extra, dict):
        raise VaultError("Extra must be an object.")
    stamp = _now()
    with _connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO items (kind, title, body, extra, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, title, body, json.dumps(extra, sort_keys=True), stamp, stamp),
        )
        item_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row(row)


def list_items(path: Path) -> list[VaultItem]:
    if not path.is_file():
        return []
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY kind ASC, id ASC"
        ).fetchall()
    return [_row(row) for row in rows]


def grouped_items(path: Path) -> dict[str, list[VaultItem]]:
    grouped = {kind: [] for kind in KINDS}
    for item in list_items(path):
        grouped.setdefault(item.kind, []).append(item)
    return grouped


def payload(path: Path | None = None) -> dict[str, Any]:
    db = path if path is not None else default_db_path()
    items = list_items(db)
    by_kind = grouped_items(db)
    return {
        "ledger": "firefly",
        "is_ledger": False,
        "items": [item.to_dict() for item in items],
        "by_kind": {
            kind: [item.to_dict() for item in by_kind[kind]] for kind in KINDS
        },
    }
