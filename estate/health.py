"""Financial freshness from Firefly account activity and bills. No second ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from enum import Enum
from typing import Iterable

_CENTS = Decimal("0.01")
ESTIMATE_LOOKBACK_DAYS = 365
ESTIMATE_LABEL = "estimate"
SOURCE_HISTORICAL = "historical_average"
SOURCE_MIDPOINT = "range_midpoint"
SOURCE_DEPOSIT_RUN_RATE = "deposit_run_rate"
SOURCE_BILL_SCHEDULE = "firefly_bills"
FORECAST_WINDOWS = (30, 60, 90)
FORECAST_HORIZON_DAYS = 90


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
    statement_date: date | None = None
    imported_date: date | None = None
    reconciled_through: date | None = None
    oldest_unreconciled: date | None = None


@dataclass(frozen=True)
class BillFreshness:
    id: str
    name: str
    last_paid: date | None
    next_expected: date | None
    overdue: bool
    age_days: int | None
    status: Status
    amount: str | None = None
    currency: str | None = None
    frequency: str | None = None
    payee: str | None = None
    pay_from: str | None = None
    amount_estimate: str | None = None
    expected_next_amount: str | None = None
    estimate_label: str | None = None
    estimate_source: str | None = None
    payment_count: int = 0
    pay_dates: tuple[date, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ForecastWindow:
    days: int
    bills: str
    income: str
    net: str
    bill_count: int
    estimate_label: str
    bills_source: str
    income_source: str


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
    oldest_unreconciled: date | None = None
    oldest_unreconciled_account: str | None = None
    last_import_at: date | None = None
    accounts: tuple[AccountFreshness, ...] = field(default_factory=tuple)
    bills: tuple[BillFreshness, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    forecast: tuple[ForecastWindow, ...] = field(default_factory=tuple)


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


def _worse(left: Status, right: Status) -> Status:
    return left if _WORST[left] >= _WORST[right] else right


def _truthy_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def iter_splits(transactions: list[dict] | None):
    for group in transactions or []:
        if not isinstance(group, dict):
            continue
        attributes = group.get("attributes") or {}
        group_day = parse_day(attributes.get("date"))
        splits = attributes.get("transactions") or []
        if not isinstance(splits, list):
            continue
        for split in splits:
            if isinstance(split, dict):
                yield split, group_day


def _split_day(split: dict, group_day: date | None) -> date | None:
    return parse_day(split.get("date")) or group_day


def _touches_account(split: dict, account_id: str) -> bool:
    return str(split.get("source_id") or "") == account_id or str(
        split.get("destination_id") or ""
    ) == account_id


def _is_imported_split(split: dict) -> bool:
    return bool(
        str(split.get("import_hash_v2") or "").strip()
        or str(split.get("external_id") or "").strip()
    )


def _last_import_across(rows: list[AccountFreshness]) -> date | None:
    dates = [row.imported_date for row in rows if row.imported_date is not None]
    return max(dates) if dates else None


def _oldest_unreconciled_across(
    rows: list[AccountFreshness],
) -> tuple[date | None, str | None]:
    dated = [row for row in rows if row.oldest_unreconciled is not None]
    if not dated:
        return None, None
    oldest = min(dated, key=lambda row: row.oldest_unreconciled or date.max)
    return oldest.oldest_unreconciled, oldest.name


def account_from_firefly(
    payload: dict,
    *,
    as_of: date,
    threshold_days: int,
    warning_lead_days: int,
    transactions: list[dict] | None = None,
) -> AccountFreshness:
    attributes = payload.get("attributes") or {}
    account_id = str(payload.get("id") or "")
    last_activity = parse_day(attributes.get("last_activity")) or parse_day(
        attributes.get("last_activity_date")
    )
    age = (as_of - last_activity).days if last_activity is not None else None
    unrec: list[date] = []
    rec: list[date] = []
    imported: list[date] = []
    statement: list[date] = []
    for split, group_day in iter_splits(transactions):
        if not _touches_account(split, account_id):
            continue
        day = _split_day(split, group_day)
        if day is None:
            continue
        if _truthy_flag(split.get("reconciled")):
            rec.append(day)
        else:
            unrec.append(day)
        if _is_imported_split(split):
            imported.append(day)
        for extra in (split.get("process_date"), split.get("invoice_date")):
            extra_day = parse_day(extra)
            if extra_day is not None:
                statement.append(extra_day)
    oldest_unreconciled = min(unrec) if unrec else None
    if oldest_unreconciled is not None:
        reconciled_through = oldest_unreconciled - timedelta(days=1)
    elif rec:
        reconciled_through = max(rec)
    else:
        reconciled_through = None
    recon_age = (
        (as_of - oldest_unreconciled).days if oldest_unreconciled is not None else None
    )
    if last_activity is None and oldest_unreconciled is None:
        status = Status.EMPTY
    elif last_activity is None:
        status = classify_age(recon_age, threshold_days, warning_lead_days)
    elif oldest_unreconciled is None:
        status = classify_age(age, threshold_days, warning_lead_days)
    else:
        status = _worse(
            classify_age(age, threshold_days, warning_lead_days),
            classify_age(recon_age, threshold_days, warning_lead_days),
        )
    return AccountFreshness(
        id=account_id,
        name=str(attributes.get("name") or f"Account {payload.get('id')}"),
        last_activity=last_activity,
        age_days=age if age is not None else recon_age,
        status=status,
        statement_date=max(statement) if statement else None,
        imported_date=max(imported) if imported else None,
        reconciled_through=reconciled_through,
        oldest_unreconciled=oldest_unreconciled,
    )


def _bill_amount(attributes: dict) -> str | None:
    lo = attributes.get("amount_min")
    hi = attributes.get("amount_max")
    if lo in (None, "") and hi in (None, ""):
        return None
    if hi in (None, "") or str(lo) == str(hi):
        return str(lo)
    return f"{lo}–{hi}"


def parse_money(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return abs(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _format_money(value: Decimal) -> str:
    return str(value.quantize(_CENTS, rounding=ROUND_HALF_EVEN))


def historical_average(amounts: Iterable[Decimal]) -> Decimal | None:
    values = sorted(abs(amount) for amount in amounts)
    if not values:
        return None
    total = sum(values, Decimal("0"))
    return (total / Decimal(len(values))).quantize(_CENTS, rounding=ROUND_HALF_EVEN)


def range_midpoint(minimum: object, maximum: object) -> Decimal | None:
    lo = parse_money(minimum)
    hi = parse_money(maximum)
    if lo is None and hi is None:
        return None
    if lo is None:
        return hi.quantize(_CENTS, rounding=ROUND_HALF_EVEN) if hi is not None else None
    if hi is None:
        return lo.quantize(_CENTS, rounding=ROUND_HALF_EVEN)
    return ((lo + hi) / Decimal(2)).quantize(_CENTS, rounding=ROUND_HALF_EVEN)


def _in_lookback(day: date | None, *, as_of: date, lookback_days: int) -> bool:
    if day is None:
        return True
    start = as_of - timedelta(days=lookback_days)
    return start <= day <= as_of


def _payment_amounts(
    payload: dict,
    *,
    as_of: date,
    transactions: list[dict] | None,
    lookback_days: int,
) -> list[Decimal]:
    bill_id = str(payload.get("id") or "")
    from_splits: list[Decimal] = []
    for split, group_day in iter_splits(transactions):
        if bill_id and str(split.get("bill_id") or "") != bill_id:
            continue
        if not bill_id:
            continue
        day = _split_day(split, group_day)
        if not _in_lookback(day, as_of=as_of, lookback_days=lookback_days):
            continue
        money = parse_money(split.get("amount"))
        if money is not None:
            from_splits.append(money)
    if from_splits:
        return from_splits
    attributes = payload.get("attributes") or {}
    from_paid: list[Decimal] = []
    paid = attributes.get("paid_dates") or []
    if not isinstance(paid, list):
        paid = [paid]
    for item in paid:
        if not isinstance(item, dict):
            continue
        day = parse_day(item.get("date"))
        if not _in_lookback(day, as_of=as_of, lookback_days=lookback_days):
            continue
        money = parse_money(item.get("amount"))
        if money is not None:
            from_paid.append(money)
    return from_paid


def _bill_estimate(
    payload: dict,
    *,
    as_of: date,
    transactions: list[dict] | None,
    lookback_days: int,
) -> tuple[str | None, str | None, int]:
    amounts = _payment_amounts(
        payload,
        as_of=as_of,
        transactions=transactions,
        lookback_days=lookback_days,
    )
    average = historical_average(amounts)
    if average is not None:
        text = _format_money(average)
        return text, SOURCE_HISTORICAL, len(amounts)
    attributes = payload.get("attributes") or {}
    midpoint = range_midpoint(attributes.get("amount_min"), attributes.get("amount_max"))
    if midpoint is None:
        return None, None, 0
    return _format_money(midpoint), SOURCE_MIDPOINT, 0


def bill_from_firefly(
    payload: dict,
    *,
    as_of: date,
    transactions: list[dict] | None = None,
    estimate_lookback_days: int = ESTIMATE_LOOKBACK_DAYS,
) -> BillFreshness | None:
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
    name = str(attributes.get("name") or f"Bill {payload.get('id')}")
    pay_from = (
        attributes.get("source_name")
        or attributes.get("account_name")
        or attributes.get("from_name")
    )
    estimate, source, payment_count = _bill_estimate(
        payload,
        as_of=as_of,
        transactions=transactions,
        lookback_days=estimate_lookback_days,
    )
    return BillFreshness(
        id=str(payload.get("id") or ""),
        name=name,
        last_paid=last_paid,
        next_expected=next_expected or (due[0] if due else None),
        overdue=overdue,
        age_days=age,
        status=status,
        amount=_bill_amount(attributes),
        currency=str(attributes.get("currency_code") or "") or None,
        frequency=str(attributes.get("repeat_freq") or "") or None,
        payee=str(attributes.get("object_group_title") or name),
        pay_from=str(pay_from).strip() if pay_from else None,
        amount_estimate=estimate,
        expected_next_amount=estimate,
        estimate_label=ESTIMATE_LABEL if estimate is not None else None,
        estimate_source=source,
        payment_count=payment_count,
        pay_dates=tuple(sorted(pay_dates)),
    )


def _occurrence_dates(bill: BillFreshness, *, as_of: date, horizon_end: date) -> list[date]:
    seen: set[date] = set()
    out: list[date] = []

    def add(day: date | None) -> None:
        if day is None or day in seen:
            return
        seen.add(day)
        out.append(day)

    for day in bill.pay_dates:
        if as_of < day <= horizon_end:
            add(day)
    if bill.next_expected is not None and as_of < bill.next_expected <= horizon_end:
        add(bill.next_expected)
    if bill.overdue:
        add(as_of)
    return out


def _deposit_total(
    transactions: list[dict] | None,
    *,
    as_of: date,
    lookback_days: int,
) -> Decimal:
    total = Decimal("0")
    for split, group_day in iter_splits(transactions):
        if str(split.get("type") or "").strip().lower() != "deposit":
            continue
        day = _split_day(split, group_day)
        if not _in_lookback(day, as_of=as_of, lookback_days=lookback_days):
            continue
        money = parse_money(split.get("amount"))
        if money is not None:
            total += money
    return total


def cash_forecast(
    bills: Iterable[BillFreshness],
    transactions: list[dict] | None,
    *,
    as_of: date,
    lookback_days: int = ESTIMATE_LOOKBACK_DAYS,
    windows: tuple[int, ...] = FORECAST_WINDOWS,
) -> tuple[ForecastWindow, ...]:
    horizon = max(windows) if windows else FORECAST_HORIZON_DAYS
    horizon_end = as_of + timedelta(days=horizon)
    deposit_total = _deposit_total(
        transactions, as_of=as_of, lookback_days=lookback_days
    )
    divisor = Decimal(max(1, lookback_days))
    rows: list[ForecastWindow] = []
    for days in windows:
        window_end = as_of + timedelta(days=days)
        bill_total = Decimal("0")
        bill_count = 0
        for bill in bills:
            amount = parse_money(bill.amount_estimate)
            if amount is None:
                continue
            for due in _occurrence_dates(bill, as_of=as_of, horizon_end=horizon_end):
                if due <= window_end:
                    bill_total += amount
                    bill_count += 1
        income = (deposit_total * Decimal(days) / divisor).quantize(
            _CENTS, rounding=ROUND_HALF_EVEN
        )
        bills_out = bill_total.quantize(_CENTS, rounding=ROUND_HALF_EVEN)
        net = (income - bills_out).quantize(_CENTS, rounding=ROUND_HALF_EVEN)
        rows.append(
            ForecastWindow(
                days=days,
                bills=_format_money(bills_out),
                income=_format_money(income),
                net=_format_money(net),
                bill_count=bill_count,
                estimate_label=ESTIMATE_LABEL,
                bills_source=SOURCE_BILL_SCHEDULE,
                income_source=SOURCE_DEPOSIT_RUN_RATE,
            )
        )
    return tuple(rows)


def assess(
    *,
    firefly_ok: bool,
    firefly_error: str | None,
    accounts: list[dict],
    bills: list[dict] | None = None,
    transactions: list[dict] | None = None,
    threshold_days: int = 30,
    warning_lead_days: int = 7,
    as_of: date | None = None,
    last_estate_sync: str | None = None,
) -> HealthReport:
    as_of = as_of or datetime.now(timezone.utc).date()
    bill_rows = tuple(
        row
        for item in (bills or [])
        if (
            row := bill_from_firefly(item, as_of=as_of, transactions=transactions)
        )
        is not None
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

    forecast_rows = cash_forecast(bill_rows, transactions, as_of=as_of)

    rows = [
        account_from_firefly(
            item,
            as_of=as_of,
            threshold_days=threshold_days,
            warning_lead_days=warning_lead_days,
            transactions=transactions,
        )
        for item in accounts
    ]
    tracked = [row for row in rows if row.status is not Status.EMPTY]
    unused = [row for row in rows if row.status is Status.EMPTY]
    notes: list[str] = []
    oldest_unrec_day, oldest_unrec_name = _oldest_unreconciled_across(rows)
    last_import_at = _last_import_across(rows)

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
                forecast=forecast_rows,
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
            forecast=forecast_rows,
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
                oldest_unreconciled=oldest_unrec_day,
                oldest_unreconciled_account=oldest_unrec_name,
                last_import_at=last_import_at,
                accounts=tuple(rows),
                bills=bill_rows,
                notes=tuple(notes),
                forecast=forecast_rows,
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
            oldest_unreconciled=oldest_unrec_day,
            oldest_unreconciled_account=oldest_unrec_name,
            last_import_at=last_import_at,
            accounts=tuple(rows),
            bills=bill_rows,
            notes=(f"No asset account has recorded activity yet ({names}).",),
            forecast=forecast_rows,
        )

    worst = max(tracked, key=lambda row: _rank(row.status, row.age_days))
    stale_name = worst.name if worst.status in {Status.STALE, Status.WARNING} else None
    if worst.status == Status.STALE:
        if worst.oldest_unreconciled is not None:
            notes.append(
                f"{worst.name} has an unreconciled Firefly transaction from {worst.oldest_unreconciled.isoformat()}."
            )
        else:
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
        oldest_unreconciled=oldest_unrec_day,
        oldest_unreconciled_account=oldest_unrec_name,
        last_import_at=last_import_at,
        accounts=tuple(rows),
        bills=bill_rows,
        notes=tuple(notes),
        forecast=forecast_rows,
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
        "oldest_unreconciled": report.oldest_unreconciled.isoformat()
        if report.oldest_unreconciled
        else None,
        "oldest_unreconciled_account": report.oldest_unreconciled_account,
        "last_import_at": report.last_import_at.isoformat() if report.last_import_at else None,
        "notes": list(report.notes),
        "accounts": [
            {
                "id": row.id,
                "name": row.name,
                "last_activity": row.last_activity.isoformat() if row.last_activity else None,
                "statement_date": row.statement_date.isoformat() if row.statement_date else None,
                "imported_date": row.imported_date.isoformat() if row.imported_date else None,
                "reconciled_through": row.reconciled_through.isoformat() if row.reconciled_through else None,
                "oldest_unreconciled": row.oldest_unreconciled.isoformat() if row.oldest_unreconciled else None,
                "age_days": row.age_days,
                "status": row.status.value,
            }
            for row in report.accounts
        ],
        "bills": [
            {
                "id": row.id,
                "name": row.name,
                "payee": row.payee,
                "amount": row.amount,
                "currency": row.currency,
                "frequency": row.frequency,
                "pay_from": row.pay_from,
                "amount_estimate": row.amount_estimate,
                "expected_next_amount": row.expected_next_amount,
                "estimate_label": row.estimate_label,
                "estimate_source": row.estimate_source,
                "payment_count": row.payment_count,
                "last_paid": row.last_paid.isoformat() if row.last_paid else None,
                "next_expected": row.next_expected.isoformat() if row.next_expected else None,
                "overdue": row.overdue,
                "age_days": row.age_days,
                "status": row.status.value,
            }
            for row in report.bills
        ],
        "forecast": [
            {
                "days": row.days,
                "bills": row.bills,
                "income": row.income,
                "net": row.net,
                "bill_count": row.bill_count,
                "estimate_label": row.estimate_label,
                "bills_source": row.bills_source,
                "income_source": row.income_source,
            }
            for row in report.forecast
        ],
    }
