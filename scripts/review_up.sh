#!/usr/bin/env bash
# Try an open PR or branch at Estate :8190 without touching stable Firefly data.
# Usage: ./scripts/review_up.sh 21
#        ./scripts/review_up.sh us-005-name-blocking-account
#        REVIEW_ISOLATED=1 ./scripts/review_up.sh 21
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <pr-number-or-branch>" >&2
  exit 2
fi

PRIMARY="$(cd "$(dirname "$0")/.." && pwd)"
REVIEW_DIR="${ESTATE_REVIEW_DIR:-$HOME/Documents/EstateVault-review}"
REF="$1"
REPO="JamesRothering/EstateVault"

git -C "$PRIMARY" fetch origin --quiet

if [[ "$REF" =~ ^[0-9]+$ ]]; then
  BRANCH="$(gh pr view "$REF" --repo "$REPO" --json headRefName --jq .headRefName)"
else
  BRANCH="$REF"
fi

git -C "$PRIMARY" fetch origin "$BRANCH" --quiet || git -C "$PRIMARY" fetch origin --quiet

if [[ -d "$REVIEW_DIR" ]]; then
  git -C "$REVIEW_DIR" fetch origin --quiet
  git -C "$REVIEW_DIR" checkout --quiet "$BRANCH" || git -C "$REVIEW_DIR" checkout --quiet -B "$BRANCH" "origin/$BRANCH"
  git -C "$REVIEW_DIR" pull --ff-only --quiet origin "$BRANCH" || true
else
  git -C "$PRIMARY" worktree add "$REVIEW_DIR" "$BRANCH" || \
    git -C "$PRIMARY" worktree add -B "$BRANCH" "$REVIEW_DIR" "origin/$BRANCH"
fi

if [[ ! -f "$REVIEW_DIR/.env" && -f "$PRIMARY/.env" ]]; then
  cp "$PRIMARY/.env" "$REVIEW_DIR/.env"
fi
for f in docker-compose.review.yml docker-compose.review-estate.yml; do
  if [[ ! -f "$REVIEW_DIR/$f" && -f "$PRIMARY/$f" ]]; then
    cp "$PRIMARY/$f" "$REVIEW_DIR/$f"
  fi
done

cd "$REVIEW_DIR"

if [[ "${REVIEW_ISOLATED:-}" == "1" ]]; then
  docker compose -p estatevault-review -f docker-compose.review.yml up -d
  echo "Isolated Firefly http://127.0.0.1:8180"
  echo "Isolated Estate  http://127.0.0.1:8190"
  exit 0
fi

if docker inspect estatevault_firefly >/dev/null 2>&1; then
  docker compose -p estatevault-review-estate -f docker-compose.review-estate.yml up -d
  echo "Review Estate http://127.0.0.1:8190 (uses stable Firefly)"
  echo "Stable Firefly remains http://127.0.0.1:8080"
else
  echo "Stable Firefly is not running; starting an isolated review stack." >&2
  docker compose -p estatevault-review -f docker-compose.review.yml up -d
  echo "Isolated Firefly http://127.0.0.1:8180"
  echo "Isolated Estate  http://127.0.0.1:8190"
fi
