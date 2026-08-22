#!/usr/bin/env bash
# One-time: register a macOS self-hosted runner so acceptance.yml can bind :8180/:8190.
# Runner lives outside the git repo. Does not merge, does not touch stable Compose.
set -euo pipefail

REPO="${ESTATE_REPO:-JamesRothering/EstateVault}"
DIR="${ESTATE_RUNNER_DIR:-$HOME/estatevault-actions-runner}"
NAME="${ESTATE_RUNNER_NAME:-estatevault-mac}"

mkdir -p "$DIR"
cd "$DIR"

if [[ ! -x ./run.sh ]]; then
  tag="$(gh api repos/actions/runner/releases/latest --jq .tag_name)"
  version="${tag#v}"
  tarball="actions-runner-osx-x64-${version}.tar.gz"
  url="https://github.com/actions/runner/releases/download/${tag}/${tarball}"
  curl -fsSL -o "$tarball" "$url"
  tar xzf "$tarball"
  rm -f "$tarball"
fi

if [[ ! -f .runner ]]; then
  token="$(gh api --method POST "repos/${REPO}/actions/runners/registration-token" --jq .token)"
  ./config.sh --unattended \
    --url "https://github.com/${REPO}" \
    --token "$token" \
    --name "$NAME" \
    --labels "macOS,acceptance" \
    --work "_work"
fi

echo "Runner configured in $DIR"
echo "Start it with: $DIR/run.sh"
echo "Keep Docker Desktop running. GitHub-hosted CI still only runs unit tests."
