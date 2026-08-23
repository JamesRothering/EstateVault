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

export COMPOSE_PROGRESS=plain
echo "starting isolated review stack $(date -u +%H:%M:%SZ)"
if ! docker compose -p estatevault-review -f docker-compose.review.yml up -d; then
  echo "compose up failed (often a cold MariaDB). retrying once after 30s"
  sleep 30
  docker compose -p estatevault-review -f docker-compose.review.yml up -d
fi

python3 scripts/wait_http.py --url http://127.0.0.1:8190/api/health --name Estate --timeout 180 --interval 10
python3 scripts/wait_http.py --url http://127.0.0.1:8180 --name Firefly --timeout 900 --interval 10

if [[ -n "${PR_NUMBER:-}" ]]; then
  printf '%s\n' "$PR_NUMBER" > "$STATE"
fi

echo "Acceptance Firefly http://127.0.0.1:8180"
echo "Acceptance Estate  http://127.0.0.1:8190"
echo "Stable (if running) is unchanged on :8080 / :8090"
