"""Financial freshness from Firefly account activity. No second ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum


class Status(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    EMPTY = "EMPTY"
    CURRENT = "CURRENT"
    WARNING = "WARNING"
    STALE = "STALE"


_WORST = {
    Status.STALE: 4,
    Status.WARNING: 3,
    Status.EMPTY: 2,
    Status.UNAVAILABLE: 1,
    Status.CURRENT: 0,
}


@dataclass(frozen=True)
class AccountFreshness:
    id: str
    name: str
    last_activity: date | None
    age_days: int | None
    status: Status


@dataclass(frozen=True)
class HealthReport:
    status: Status
    threshold_days: int
    warning_lead_days: int
    as_of: date
    firefly_ok: bool
    firefly_error: str | None
    last_estate_sync: str | None
    stale_account: str | None
    accounts: tuple[AccountFreshness, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


def parse_day(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def classify_age(age_days: int | None, threshold_days: int, warning_lead_days: int) -> Status:
    if age_days is None:
        return Status.EMPTY
    if age_days > threshold_days:
        return Status.STALE
    warn_after = max(0, threshold_days - warning_lead_days)
    if age_days > warn_after:
        return Status.WARNING
    return Status.CURRENT


def account_from_firefly(
    payload: dict,
    *,
    as_of: date,
    threshold_days: int,
    warning_lead_days: int,
) -> AccountFreshness:
    attributes = payload.get("attributes") or {}
    last_activity = parse_day(attributes.get("last_activity")) or parse_day(
        attributes.get("last_activity_date")
    )
    age = (as_of - last_activity).days if last_activity is not None else None
    return AccountFreshness(
        id=str(payload.get("id") or ""),
        name=str(attributes.get("name") or f"Account {payload.get('id')}"),
        last_activity=last_activity,
        age_days=age,
        status=classify_age(age, threshold_days, warning_lead_days),
    )


def assess(
    *,
    firefly_ok: bool,
    firefly_error: str | None,
    accounts: list[dict],
    threshold_days: int = 30,
    warning_lead_days: int = 7,
    as_of: date | None = None,
    last_estate_sync: str | None = None,
) -> HealthReport:
    as_of = as_of or datetime.now(timezone.utc).date()
    if not firefly_ok:
        return HealthReport(
            status=Status.UNAVAILABLE,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            as_of=as_of,
            firefly_ok=False,
            firefly_error=firefly_error or "Firefly API is not reachable.",
            last_estate_sync=last_estate_sync,
            stale_account=None,
            notes=(
                "Financial information is not trustworthy until Firefly answers.",
            ),
        )

    rows = [
        account_from_firefly(
            item,
            as_of=as_of,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
        )
        for item in accounts
    ]
    if not rows:
        return HealthReport(
            status=Status.EMPTY,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            as_of=as_of,
            firefly_ok=True,
            firefly_error=None,
            last_estate_sync=last_estate_sync,
            stale_account=None,
            notes=(
                "Firefly has no asset accounts yet. This is not CURRENT.",
            ),
        )

    tracked = [row for row in rows if row.status is not Status.EMPTY]
    unused = [row for row in rows if row.status is Status.EMPTY]
    notes: list[str] = []
    if not tracked:
        names = ", ".join(row.name for row in unused) or "accounts"
        return HealthReport(
            status=Status.EMPTY,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            as_of=as_of,
            firefly_ok=True,
            firefly_error=None,
            last_estate_sync=last_estate_sync,
            stale_account=unused[0].name if unused else None,
            accounts=tuple(rows),
            notes=(f"No asset account has recorded activity yet ({names}).",),
        )

    worst = max(tracked, key=lambda row: (_WORST[row.status], row.age_days or -1))
    stale_name = worst.name if worst.status in {Status.STALE, Status.WARNING} else None
    if worst.status == Status.STALE:
        notes.append(f"{worst.name} is past the {threshold_days}-day freshness window.")
    elif worst.status == Status.WARNING:
        notes.append(f"{worst.name} will be STALE if not maintained within the window.")
    if unused:
        names = ", ".join(row.name for row in unused)
        notes.append(
            f"Unused (no activity, not counted toward overall status): {names}."
        )

    return HealthReport(
        status=worst.status,
        threshold_days=threshold_days,
        warning_lead_days=warning_lead_days,
        as_of=as_of,
        firefly_ok=True,
        firefly_error=None,
        last_estate_sync=last_estate_sync,
        stale_account=stale_name,
        accounts=tuple(rows),
        notes=tuple(notes),
    )


def report_to_dict(report: HealthReport) -> dict:
    return {
        "status": report.status.value,
        "threshold_days": report.threshold_days,
        "warning_lead_days": report.warning_lead_days,
        "as_of": report.as_of.isoformat(),
        "firefly_ok": report.firefly_ok,
        "firefly_error": report.firefly_error,
        "last_estate_sync": report.last_estate_sync,
        "stale_account": report.stale_account,
        "notes": list(report.notes),
        "accounts": [
            {
                "id": row.id,
                "name": row.name,
                "last_activity": row.last_activity.isoformat() if row.last_activity else None,
                "age_days": row.age_days,
                "status": row.status.value,
            }
            for row in report.accounts
        ],
    }
