# Architecture (starting hypothesis, implemented thinly)

```
Estate dashboard  :8090     Firefly III UI  :8080
        │                         │
        ▼                         ▼
  estate Python             fireflyiii/core
  health + API              (ledger of record)
        │                         │
        └──── Firefly API ────────┘
                    │
                 MariaDB
```

## Rules

1. Firefly is the only financial ledger. Estate does not store transactions.
2. If Firefly is unreachable or unauthenticated, status is `UNAVAILABLE`, never `CURRENT`.
3. If there are no asset accounts, status is `EMPTY`, never `CURRENT`.
4. Overall status is the **worst** asset account (`STALE` > `WARNING` > `EMPTY` > `CURRENT`).
5. Family users (later) must not receive `FIREFLY_TOKEN`.

## Freshness (slice 1)

- Input: Firefly asset accounts’ `last_activity`.
- `FRESHNESS_THRESHOLD_DAYS` (default 30).
- `WARNING_LEAD_DAYS` (default 7): age in `(threshold - lead, threshold]` is `WARNING`.
- Next: per-account reconciliation and unreconciled transaction search.

## States (full machine; only the first four are computed today)

`CURRENT` → `WARNING` → `STALE` → `ESTATE TRANSITION` → `ESTATE ACTIVE`

Transition/Active require notifications + family auth (later stories).
