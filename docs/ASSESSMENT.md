# Firefly III and related-project assessment

Inspected 2026-08-18. Firefly source was cloned read-only to `/tmp/firefly-iii-src`; it is **not** in this repository.

## Firefly III (`firefly-iii/firefly-iii`)

| Area | What it is |
|---|---|
| Stack | PHP / Laravel, Vue front-end, PHPUnit |
| Database | MySQL/MariaDB (official compose) or PostgreSQL |
| API | JSON API v1, Personal Access Tokens and OAuth. `Authorization: Bearer` |
| Auth | Built-in user DB (`AUTHENTICATION_GUARD=web`); remote-user guard for SSO later |
| Deploy | Official `fireflyiii/core` image + DB + optional cron + **separate** Data Importer image |
| License | AGPL-3.0-or-later |
| Plugins | No first-class plugin system that would replace an Estate app. Integrations are API + importer |

**Already provides (use it, do not rebuild):** accounts, transactions, categories, budgets, bills/subscriptions, recurring transactions, rules, reconciliation (transaction `reconciled` flag), reports, CSV/bank import (via Data Importer), web UI for day-to-day bookkeeping.

**API we need for Estate health:** `GET /api/v1/about`, `GET /api/v1/accounts?type=asset` (includes `last_activity`), `GET /api/v1/bills?start=&end=` (`pay_dates` / `paid_dates`), later `GET /api/v1/search/transactions?query=reconciled:false`, recurrences.

**Belongs in Firefly:** any number that is a ledger fact (balances, txns, bills as Firefly bills, reconciliation clicks).

**Belongs in Estate:** freshness/heartbeat state machine, family-facing status that must not lie, estate documents/contacts/instructions, roles that must not receive the Firefly PAT, notifications, dead-man’s-switch *policy* (when freshness becomes transition).

**Limitations:** Firefly has no estate/beneficiary model, no “data is stale” family dashboard, no dead-man’s-switch. Account `last_activity` is a proxy for maintenance; true reconciliation age needs per-transaction `reconciled` (next stories). Import freshness lives partly in the Data Importer, not core. Firefly users who can log in see the whole ledger — do not give family Firefly accounts until a later, deliberate story.

## Repository strategy

| Choice | Decision |
|---|---|
| Fork Firefly? | **No.** Upstream updates would become a merge nightmare. |
| Clone Firefly into this repo? | **No.** Run the published Docker image. |
| This repo | **Standalone GitHub repo** (`JamesRothering/EstateVault`), not in AutoApply’s fork network. Commits here can count on the profile graph. |
| Upstream relationship | Pin `fireflyiii/core:latest` (or a digest later). Pull image updates; never vendor PHP. |

## Local / Mac

Docker Desktop + Compose. Firefly at `http://127.0.0.1:8080`, Estate at `http://127.0.0.1:8090`. CareerManager already uses Postgres `5432` and Redis `6379`; this compose uses MariaDB in-network and does not bind 5432.

## Dead-man’s-switch and adjacent projects (conceptual borrow only)

| Project | Stack / license | Heartbeat | Beneficiary | Borrow |
|---|---|---|---|---|
| [circa10a/dead-mans-switch](https://github.com/circa10a/dead-mans-switch) | Go, SQLite, MIT | Explicit check-in / reset timers; Shoutrrr notifications | N/A (message on expiry) | Notification plumbing later; **not** our heartbeat (we use financial maintenance) |
| [giovantenne/lastsignal](https://github.com/giovantenne/lastsignal) | Rails 8, SQLite, MIT, E2EE | Email check-ins; 30-day default; state: Active → Grace → Cooldown → Delivered | Recipients decrypt with passphrase | **State machine + 30-day default + reminder ladder.** Do not copy E2EE until we store secrets. Optional `/webhooks/keepalive` is the anti-pattern for us (separate click). |
| [slavhate/legacy-vault](https://github.com/slavhate/legacy-vault) | Node/Express, SQLite, MIT, AES-256-GCM | Explicit check-in | Tokens, emergency request with waiting period, vault sections (insurance, property, contacts) | **Vault section list** and audit log. Check-in button is what we are avoiding as the *primary* heartbeat. |
| [alpyxn/aeterna](https://github.com/alpyxn/aeterna) | Go, GPL-3.0 | Self-hosted DMS | Digital legacy | Ideas only; GPL would infect if we copied code. We will not. |
| [jbms/beancount-import](https://github.com/jbms/beancount-import) | Python, GPL-2.0 | n/a | n/a | Import UX ideas; Firefly Data Importer is the actual importer. |
| [actualbudget/actual](https://github.com/actualbudget/actual) | TS, MIT, local-first | n/a | n/a | Competing ledger. We picked Firefly. Do not run both. |

**Heartbeat decision:** LastSignal/Legacy Vault assume a separate “I’m alive” action. James wants **successful Firefly maintenance** to reset freshness. Estate computes CURRENT from Firefly; that *is* the heartbeat. Explicit check-in is a later optional override, not MVP.

## Simplest architecture that preserves the split

Same as the prompt diagram, minus forecasting and documents until those stories:

`Estate UI (8090)` → `estate` Python process → Firefly API → `Firefly III + MariaDB`.

No Estate database in slice 1. Config is `.env`. When we need estate documents and DMS audit, add SQLite in Estate only (not a ledger).
