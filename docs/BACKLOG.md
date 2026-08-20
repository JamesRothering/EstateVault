# Backlog

Overnight and daytime work pick GitHub issues labeled **ready**. Do not invent a second ledger.

**Judge:** Given/When/Then on the story, tests red then green, PR unless it is the initial slice on `main`.

## First vertical slice (implemented on `main`)

- **US-001** Run Firefly III locally with Compose (official image).
- **US-002** Connect Estate with a Firefly Personal Access Token.
- **US-003** Dashboard shows CURRENT / WARNING / STALE / EMPTY / UNAVAILABLE from Firefly.
- **US-004** Freshness window configurable (default 30 days).
- **US-005** Name the account that blocks CURRENT.
- **US-006** Unused asset accounts (no `last_activity`) do not set overall status to EMPTY.
- **US-013** Overdue Firefly bills block CURRENT (inactive bills ignored; no bills does not block).

## Next — Financial health

- **US-010** Per-account reconciliation dates (statement / imported / reconciled).
- **US-011** Oldest unreconciled Firefly transaction (`reconciled:false`).
- **US-012** Last successful import/sync timestamp (Data Importer + Firefly).

## Bill management

- **US-020** Consolidated bill view from Firefly bills + last payment.
- **US-021** Historical average / expected next amount (deterministic, labeled estimate).
- **US-022** Due date, pay-from account, notes that Firefly does not store.

## Forecasting

- **US-030** 30/60/90-day expected bills vs income (simple, labeled estimates).
- **US-031** Warn when a month’s projected outflow exceeds expected cash.

## Estate metadata (not in Firefly)

- **US-040** Contacts, documents, instructions, insurance, property, vehicles.
- **US-041** “How to handle this account” notes linked to a Firefly account id.

## Family access

- **US-050** Owner / Estate Administrator / read-only beneficiary. No Firefly PAT in family sessions.

## Dead man’s switch

- **US-060** Map freshness to CURRENT → WARNING → STALE (already started).
- **US-061** Notifications on WARNING and STALE.
- **US-062** ESTATE TRANSITION after configurable stale period; audit; cancel/recover.

## Security

- **US-070** Secrets only in `.env` / Docker secrets; backups of Firefly volume + future Estate SQLite.

## Out of scope until a story says otherwise

Rewrite Firefly. Actual Budget. A second transaction store. Machine-learning bill prediction. “I’m alive” as the *primary* heartbeat.
