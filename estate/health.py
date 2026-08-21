"""Financial freshness from Firefly account activity and bills. No second ledger."""

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
class BillFreshness:
    id: str
    name: str
    last_paid: date | None
    next_expected: date | None
    overdue: bool
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
    stale_bill: str | None = None
    blocking: str | None = None
    accounts: tuple[AccountFreshness, ...] = field(default_factory=tuple)
    bills: tuple[BillFreshness, ...] = field(default_factory=tuple)
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


def _is_active(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _dates_from(values: object) -> list[date]:
    if not values:
        return []
    if not isinstance(values, list):
        day = parse_day(values)
        return [day] if day is not None else []
    out: list[date] = []
    for item in values:
        if isinstance(item, dict):
            day = parse_day(item.get("date"))
        else:
            day = parse_day(item)
        if day is not None:
            out.append(day)
    return out


def _rank(status: Status, age_days: int | None) -> tuple[int, int]:
    return (_WORST[status], age_days if age_days is not None else -1)


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


def bill_from_firefly(payload: dict, *, as_of: date) -> BillFreshness | None:
    attributes = payload.get("attributes") or {}
    if not _is_active(attributes.get("active")):
        return None
    pay_dates = _dates_from(attributes.get("pay_dates"))
    paid_dates = _dates_from(attributes.get("paid_dates"))
    next_expected = parse_day(attributes.get("next_expected_match"))
    last_paid = max(paid_dates) if paid_dates else parse_day(attributes.get("last_paid_date"))
    due = sorted(day for day in pay_dates if day <= as_of)
    overdue_on: date | None = None
    if due:
        if len(paid_dates) < len(due):
            overdue_on = due[0]
    elif next_expected is not None and next_expected <= as_of:
        if not any(paid >= next_expected for paid in paid_dates):
            overdue_on = next_expected
    overdue = overdue_on is not None
    age = (as_of - overdue_on).days if overdue_on is not None else None
    status = Status.STALE if overdue else Status.CURRENT
    return BillFreshness(
        id=str(payload.get("id") or ""),
        name=str(attributes.get("name") or f"Bill {payload.get('id')}"),
        last_paid=last_paid,
        next_expected=next_expected or (due[0] if due else None),
        overdue=overdue,
        age_days=age,
        status=status,
    )


def assess(
    *,
    firefly_ok: bool,
    firefly_error: str | None,
    accounts: list[dict],
    bills: list[dict] | None = None,
    threshold_days: int = 30,
    warning_lead_days: int = 7,
    as_of: date | None = None,
    last_estate_sync: str | None = None,
) -> HealthReport:
    as_of = as_of or datetime.now(timezone.utc).date()
    bill_rows = tuple(
        row
        for item in (bills or [])
        if (row := bill_from_firefly(item, as_of=as_of)) is not None
    )
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
    tracked = [row for row in rows if row.status is not Status.EMPTY]
    unused = [row for row in rows if row.status is Status.EMPTY]
    notes: list[str] = []

    worst_bill = (
        max(bill_rows, key=lambda row: _rank(row.status, row.age_days)) if bill_rows else None
    )
    stale_bill = (
        worst_bill.name
        if worst_bill is not None and worst_bill.status in {Status.STALE, Status.WARNING}
        else None
    )

    if not rows:
        if worst_bill is not None and worst_bill.status is Status.STALE:
            expected = worst_bill.next_expected.isoformat() if worst_bill.next_expected else "an expected date"
            return HealthReport(
                status=Status.STALE,
                threshold_days=threshold_days,
                warning_lead_days=warning_lead_days,
                as_of=as_of,
                firefly_ok=True,
                firefly_error=None,
                last_estate_sync=last_estate_sync,
                stale_account=None,
                stale_bill=stale_bill,
                blocking=stale_bill,
                bills=bill_rows,
                notes=(
                    f"{worst_bill.name} is overdue in Firefly (expected {expected}, unpaid).",
                ),
            )
        return HealthReport(
            status=Status.EMPTY,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            as_of=as_of,
            firefly_ok=True,
            firefly_error=None,
            last_estate_sync=last_estate_sync,
            stale_account=None,
            bills=bill_rows,
            notes=(
                "Firefly has no asset accounts yet. This is not CURRENT.",
            ),
        )

    if not tracked:
        names = ", ".join(row.name for row in unused) or "accounts"
        if worst_bill is not None and worst_bill.status is Status.STALE:
            expected = worst_bill.next_expected.isoformat() if worst_bill.next_expected else "an expected date"
            notes.append(
                f"{worst_bill.name} is overdue in Firefly (expected {expected}, unpaid)."
            )
            notes.append(f"Unused (no activity, not counted toward overall status): {names}.")
            return HealthReport(
                status=Status.STALE,
                threshold_days=threshold_days,
                warning_lead_days=warning_lead_days,
                as_of=as_of,
                firefly_ok=True,
                firefly_error=None,
                last_estate_sync=last_estate_sync,
                stale_account=unused[0].name if unused else None,
                stale_bill=stale_bill,
                blocking=stale_bill,
                accounts=tuple(rows),
                bills=bill_rows,
                notes=tuple(notes),
            )
        return HealthReport(
            status=Status.EMPTY,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            as_of=as_of,
            firefly_ok=True,
            firefly_error=None,
            last_estate_sync=last_estate_sync,
            stale_account=unused[0].name if unused else None,
            stale_bill=stale_bill,
            accounts=tuple(rows),
            bills=bill_rows,
            notes=(f"No asset account has recorded activity yet ({names}).",),
        )

    worst = max(tracked, key=lambda row: _rank(row.status, row.age_days))
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
    if worst_bill is not None and worst_bill.status == Status.STALE:
        expected = worst_bill.next_expected.isoformat() if worst_bill.next_expected else "an expected date"
        notes.append(
            f"{worst_bill.name} is overdue in Firefly (expected {expected}, unpaid)."
        )

    overall_status = worst.status
    blocking = stale_name
    if worst_bill is not None and _rank(worst_bill.status, worst_bill.age_days) > _rank(
        worst.status, worst.age_days
    ):
        overall_status = worst_bill.status
        blocking = stale_bill
    elif stale_bill and blocking is None:
        blocking = stale_bill
    if overall_status not in {Status.STALE, Status.WARNING}:
        blocking = None

    return HealthReport(
        status=overall_status,
        threshold_days=threshold_days,
        warning_lead_days=warning_lead_days,
        as_of=as_of,
        firefly_ok=True,
        firefly_error=None,
        last_estate_sync=last_estate_sync,
        stale_account=stale_name,
        stale_bill=stale_bill,
        blocking=blocking,
        accounts=tuple(rows),
        bills=bill_rows,
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
        "stale_bill": report.stale_bill,
        "blocking": report.blocking,
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
        "bills": [
            {
                "id": row.id,
                "name": row.name,
                "last_paid": row.last_paid.isoformat() if row.last_paid else None,
                "next_expected": row.next_expected.isoformat() if row.next_expected else None,
                "overdue": row.overdue,
                "age_days": row.age_days,
                "status": row.status.value,
            }
            for row in report.bills
        ],
    }
