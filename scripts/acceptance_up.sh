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

COMPOSE=(docker compose -p estatevault-review -f docker-compose.review.yml)
export COMPOSE_PROGRESS=plain

echo "starting isolated review db $(date -u +%H:%M:%SZ)"
if ! "${COMPOSE[@]}" up -d db; then
  echo "compose up failed (often a cold MariaDB). retrying once after 30s"
  sleep 30
  "${COMPOSE[@]}" up -d db
fi

echo "waiting for review MariaDB to become healthy"
deadline=$((SECONDS + 900))
while true; do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' estatevault_review_db 2>/dev/null || echo missing)"
  echo "review db status=${status} $(date -u +%H:%M:%SZ)"
  if [[ "$status" == healthy ]]; then
    break
  fi
  if (( SECONDS >= deadline )); then
    echo "ERROR: review MariaDB never became healthy" >&2
    "${COMPOSE[@]}" ps -a >&2
    docker logs --tail 80 estatevault_review_db >&2 || true
    exit 1
  fi
  sleep 10
done

echo "starting isolated review stack $(date -u +%H:%M:%SZ)"
"${COMPOSE[@]}" up -d || true

# Interrupted up -d leaves Firefly/Estate in Created; HTTP wait then burns the job timeout.
echo "starting any leftover Created containers"
"${COMPOSE[@]}" start
"${COMPOSE[@]}" ps -a

fail_with_ps() {
  echo "acceptance stack is not answering; compose status:" >&2
  "${COMPOSE[@]}" ps -a >&2
  exit 1
}

python3 scripts/wait_http.py --url http://127.0.0.1:8190/api/health --name Estate --timeout 180 --interval 10 || fail_with_ps
python3 scripts/wait_http.py --url http://127.0.0.1:8180 --name Firefly --timeout 900 --interval 10 || fail_with_ps

if [[ -n "${PR_NUMBER:-}" ]]; then
  printf '%s\n' "$PR_NUMBER" > "$STATE"
fi

echo "Acceptance Firefly http://127.0.0.1:8180"
echo "Acceptance Estate  http://127.0.0.1:8190"
echo "Stable (if running) is unchanged on :8080 / :8090"
