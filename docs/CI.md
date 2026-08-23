# CI, stable, and review

Estate has three layers. GitHub Actions does **not** write product code by itself. Labeling an issue `ready` starts a Cursor cloud agent that opens a PR. James merges.

## GitHub Checks

On every pull request and every push to `main`, Actions runs:

```bash
python3 -m unittest discover -s tests -v
```

and validates the Compose files. That is the check you see on the PR.

## Stable (already merged)

What family (and you) trust as the current product:

| Service | URL |
|---|---|
| Firefly | http://127.0.0.1:8080 |
| Estate | http://127.0.0.1:8090 |

```bash
./scripts/stable_up.sh
```

This uses `main` only (a `EstateVault-stable` worktree when this checkout is on another branch). It does not replace the Firefly MariaDB volume.

## Review (open PR — try before merge)

| Service | URL |
|---|---|
| Estate (PR code, stable Firefly) | http://127.0.0.1:8190 |
| Isolated Firefly (only if stable is down) | http://127.0.0.1:8180 |

```bash
./scripts/review_up.sh 21          # PR number
./scripts/review_up.sh us-005-name-blocking-account
./scripts/review_down.sh
```

Default review starts **Estate only** on 8190 and talks to the stable Firefly container, so you try the new dashboard against Wells Fargo data without cloning the ledger. Isolated full stack (`REVIEW_ISOLATED=1`) is an empty Firefly on 8180/8190 and does not touch the stable volume.

## Acceptance (each open PR, isolated)

GitHub-hosted Checks still do not run Firefly. To put a PR on this Mac automatically:

1. Install the self-hosted runner once: `./scripts/install_acceptance_runner.sh` then `$HOME/estatevault-actions-runner/run.sh` (Docker Desktop must be running). The installer sets `GITHUB_ACTIONS_RUNNER_CHANNEL_TIMEOUT=300` so this Mac is not dropped after 30s of worker startup.
2. On every open PR, workflow **Acceptance** starts Compose project `estatevault-review`: Firefly [http://127.0.0.1:8180](http://127.0.0.1:8180), Estate [http://127.0.0.1:8190](http://127.0.0.1:8190). The job **fails** unless those URLs return HTTP (not connection refused). Isolated MariaDB/Firefly use a pinned review-only DB password so a fresh Actions `.env` cannot desync from the leftover volume. `acceptance_up.sh` starts MariaDB first, starts leftover Created containers, and recreates a broken review volume only. Prints a line every 10s so the self-hosted runner does not look idle and get dropped.
3. Closing or merging the PR tears that stack down. Stable `:8080` / `:8090` and its MariaDB volume are not used.

The isolated ledger is **empty**. It is not a copy of Wells Fargo. One PR at a time on 8180/8190.

## Ready → agent → PR

1. Mark **one** issue `ready` (take `ready` off shipped issues).
2. After this workflow is on `main` and secret `CURSOR_API_KEY` exists, GitHub starts a Cursor cloud agent.
3. The agent opens a PR. It does not merge.
4. You try it on 8190, then merge when you are satisfied.

Create the API key at [Cursor Integrations](https://cursor.com/dashboard/integrations). Store it as repo secret `CURSOR_API_KEY`. Connect Cursor GitHub access to `JamesRothering/EstateVault`.

Until that secret exists, labeling `ready` comments on the issue instead of starting an agent.

Do not put `secrets.*` in a workflow `if:`. GitHub treats that file as invalid and emails a 0-second failure named `.github/workflows/ready.yml` on every push. The ready workflow copies the key into job `env` and branches on a `mode` output instead.
