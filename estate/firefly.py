"""Read-only Firefly III API client. PAT in env; never expose to family UI later."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone


class FireflyError(RuntimeError):
    pass


def _base_url() -> str:
    return os.environ.get("FIREFLY_URL", "http://127.0.0.1:8080").rstrip("/")


def _token() -> str:
    return os.environ.get("FIREFLY_TOKEN", "").strip()


def get_json(path: str, timeout: float = 15.0) -> dict:
    token = _token()
    if not token:
        raise FireflyError("FIREFLY_TOKEN is empty. Create a Personal Access Token in Firefly (Profile → OAuth).")
    url = f"{_base_url()}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise FireflyError(f"Firefly HTTP {exc.code} for {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FireflyError(f"Firefly unreachable at {_base_url()}: {exc.reason}") from exc
    return json.loads(body)


def about() -> dict:
    return get_json("/api/v1/about")


def _collection(payload: dict) -> list[dict]:
    data = payload.get("data") or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def asset_accounts() -> list[dict]:
    return _collection(get_json("/api/v1/accounts?type=asset"))


def bills(start: date, end: date) -> list[dict]:
    # start/end make Firefly fill pay_dates and paid_dates for the window.
    path = f"/api/v1/bills?start={start.isoformat()}&end={end.isoformat()}"
    return _collection(get_json(path))


def fetch_snapshot(*, lookback_days: int = 30) -> tuple[bool, str | None, list[dict], list[dict], str]:
    synced = datetime.now(timezone.utc).isoformat()
    as_of = datetime.now(timezone.utc).date()
    start = as_of - timedelta(days=max(1, lookback_days))
    try:
        about()
        accounts = asset_accounts()
        bill_rows = bills(start, as_of)
    except FireflyError as exc:
        return False, str(exc), [], [], synced
    return True, None, accounts, bill_rows, synced
