#!/usr/bin/env bash
# Stop isolated acceptance only. Leaves stable :8080 / :8090 alone.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="${ESTATE_ACCEPTANCE_STATE:-$HOME/.estatevault-acceptance-pr}"
cd "$ROOT"

if [[ -n "${PR_NUMBER:-}" && -f "$STATE" ]]; then
  current="$(tr -d '[:space:]' < "$STATE" || true)"
  if [[ -n "$current" && "$current" != "$PR_NUMBER" ]]; then
    echo "Acceptance is serving PR #${current}; not tearing down for #${PR_NUMBER}."
    exit 0
  fi
fi

docker compose -p estatevault-review -f docker-compose.review.yml down
rm -f "$STATE"
echo "Acceptance stack stopped. Stable (if running) is unchanged."
