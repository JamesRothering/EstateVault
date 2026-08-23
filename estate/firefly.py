"""Read-only Firefly III API client. PAT in env; never expose to family UI later."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from estate.health import ESTIMATE_LOOKBACK_DAYS


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


def search_transactions(query: str, *, limit: int = 50, max_pages: int = 20) -> list[dict]:
    out: list[dict] = []
    page = 1
    while page <= max_pages:
        encoded = urllib.parse.quote(query, safe="")
        payload = get_json(
            f"/api/v1/search/transactions?query={encoded}&limit={limit}&page={page}"
        )
        rows = _collection(payload)
        out.extend(rows)
        pagination = (payload.get("meta") or {}).get("pagination") or {}
        last = int(pagination.get("total_pages") or 1)
        current = int(pagination.get("current_page") or page)
        if current >= last or not rows:
            break
        page += 1
    return out


def recon_transactions() -> list[dict]:
    by_id: dict[str, dict] = {}
    for query in ("reconciled:false", "has_any_external_id:true"):
        for row in search_transactions(query):
            key = str(row.get("id") or "")
            if key:
                by_id[key] = row
    return list(by_id.values())


def bill_transactions(bill_id: str, start: date, end: date, *, limit: int = 50, max_pages: int = 20) -> list[dict]:
    out: list[dict] = []
    page = 1
    encoded = urllib.parse.quote(str(bill_id), safe="")
    while page <= max_pages:
        payload = get_json(
            f"/api/v1/bills/{encoded}/transactions"
            f"?start={start.isoformat()}&end={end.isoformat()}&limit={limit}&page={page}"
        )
        rows = _collection(payload)
        out.extend(rows)
        pagination = (payload.get("meta") or {}).get("pagination") or {}
        last = int(pagination.get("total_pages") or 1)
        current = int(pagination.get("current_page") or page)
        if current >= last or not rows:
            break
        page += 1
    return out


def _merge_transactions(*groups: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    anonymous: list[dict] = []
    for group in groups:
        for row in group:
            key = str(row.get("id") or "")
            if key:
                by_id[key] = row
            else:
                anonymous.append(row)
    return list(by_id.values()) + anonymous


def fetch_snapshot(*, lookback_days: int = 30) -> tuple[bool, str | None, list[dict], list[dict], str, list[dict]]:
    synced = datetime.now(timezone.utc).isoformat()
    as_of = datetime.now(timezone.utc).date()
    start = as_of - timedelta(days=max(1, lookback_days))
    history_start = as_of - timedelta(days=ESTIMATE_LOOKBACK_DAYS)
    try:
        about()
        accounts = asset_accounts()
        bill_rows = bills(start, as_of)
        txs = recon_transactions()
        history: list[dict] = []
        for bill in bill_rows:
            bill_id = str(bill.get("id") or "")
            if not bill_id:
                continue
            try:
                history.extend(bill_transactions(bill_id, history_start, as_of))
            except FireflyError:
                continue
        txs = _merge_transactions(txs, history)
    except FireflyError as exc:
        return False, str(exc), [], [], synced, []
    return True, None, accounts, bill_rows, synced, txs
