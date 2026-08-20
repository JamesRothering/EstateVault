# Estate Vault

Self-hosted financial system of record (**Firefly III**) plus a thin **Estate Continuity Layer** so family can tell whether the books are trustworthy if James stops maintaining them.

This GitHub repository is **standalone**. It is **not a fork of Firefly III**. Firefly runs as the official Docker image. Estate talks to Firefly’s HTTP API. Do not copy the ledger.

## Use it tonight

```bash
cd ~/Documents/EstateVault
python3 scripts/bootstrap_env.py
docker compose up -d
```

Wait until Firefly finishes migrating, then:

1. Open [http://127.0.0.1:8080](http://127.0.0.1:8080) and create the owner account.
2. Firefly → **Profile → OAuth → Personal Access Tokens** → create a token.
3. Put that token in `.env` as `FIREFLY_TOKEN=...`
4. `docker compose up -d estate` (or restart estate)
5. Open the Estate dashboard: [http://127.0.0.1:8090](http://127.0.0.1:8090)

Import and reconcile in **Firefly**. Estate only reports freshness. It will not show CURRENT if Firefly is down, the token is missing, or there are no asset accounts.

Run the dashboard on the host (Firefly still in Docker):

```bash
python3 -m estate
```

Tests (no Docker required):

```bash
python3 -m pytest -q
```

## What this first slice does

- Starts Firefly III (ledger) and MariaDB via Compose.
- Estate dashboard: **CURRENT / WARNING / STALE / EMPTY / UNAVAILABLE**.
- Uses Firefly `last_activity` per asset account. Oldest/worst account wins.
- Freshness window defaults to **30 days**, warning **7 days** before stale. Configurable in `.env`.
- Names the account that is blocking CURRENT.
- Asset accounts with **no activity** (e.g. an unused Cash wallet) stay listed but do not make the overall light EMPTY.

## What it does not do yet

Bills view, cash forecast, documents vault, family logins, dead-man’s-switch notifications. See [docs/BACKLOG.md](docs/BACKLOG.md) and GitHub issues.

## Docs

- [Architecture assessment](docs/ASSESSMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Backlog](docs/BACKLOG.md)

Firefly III is AGPL-3.0 and remains upstream. This Estate layer is MIT.
