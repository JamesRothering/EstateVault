#!/usr/bin/env bash
# Stop review containers only. Leaves stable :8080 / :8090 alone.
set -euo pipefail

PRIMARY="$(cd "$(dirname "$0")/.." && pwd)"
REVIEW_DIR="${ESTATE_REVIEW_DIR:-$HOME/Documents/EstateVault-review}"
dir="$PRIMARY"
if [[ -f "$REVIEW_DIR/docker-compose.yml" ]]; then
  dir="$REVIEW_DIR"
fi
cd "$dir"
docker compose -p estatevault-review-estate -f docker-compose.review-estate.yml down 2>/dev/null || true
  docker compose -p estatevault-review -f docker-compose.review.yml down 2>/dev/null || true
echo "Review stack stopped. Stable (if running) is unchanged."
