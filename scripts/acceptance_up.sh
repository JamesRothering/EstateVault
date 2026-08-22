#!/usr/bin/env bash
# Isolated acceptance stack for the current checkout. Never touches stable.
# Firefly :8180, Estate :8190, volumes estatevault_review_*.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="${ESTATE_ACCEPTANCE_STATE:-$HOME/.estatevault-acceptance-pr}"
cd "$ROOT"

if [[ ! -f .env ]]; then
  python3 scripts/bootstrap_env.py
fi

docker compose -p estatevault-review -f docker-compose.review.yml up -d

if [[ -n "${PR_NUMBER:-}" ]]; then
  printf '%s\n' "$PR_NUMBER" > "$STATE"
fi

echo "Acceptance Firefly http://127.0.0.1:8180"
echo "Acceptance Estate  http://127.0.0.1:8190"
echo "Stable (if running) is unchanged on :8080 / :8090"
