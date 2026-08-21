#!/usr/bin/env bash
# Bring up merged main: Firefly :8080, Estate :8090.
set -euo pipefail

PRIMARY="$(cd "$(dirname "$0")/.." && pwd)"
STABLE_DIR="${ESTATE_STABLE_DIR:-$HOME/Documents/EstateVault-stable}"

git -C "$PRIMARY" fetch origin main --quiet

branch="$(git -C "$PRIMARY" rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "main" ]]; then
  compose_dir="$PRIMARY"
else
  if [[ -d "$STABLE_DIR" ]]; then
    git -C "$STABLE_DIR" fetch origin --quiet
    git -C "$STABLE_DIR" checkout --quiet main
    git -C "$STABLE_DIR" pull --ff-only --quiet origin main
  else
    git -C "$PRIMARY" worktree add -B main "$STABLE_DIR" origin/main
  fi
  compose_dir="$STABLE_DIR"
  if [[ ! -f "$compose_dir/.env" && -f "$PRIMARY/.env" ]]; then
    cp "$PRIMARY/.env" "$compose_dir/.env"
  fi
fi

cd "$compose_dir"
docker compose -p estatevault up -d
echo "Stable Firefly http://127.0.0.1:8080"
echo "Stable Estate  http://127.0.0.1:8090"
