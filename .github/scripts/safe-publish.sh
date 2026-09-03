#!/usr/bin/env bash
set -euo pipefail
[[ "$#" -ge 2 ]] || { echo "usage: $0 <message> <path>..." >&2; exit 2; }
MESSAGE="$1"; shift; FILES=("$@")
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
SNAPSHOT="$(mktemp -d)"; trap 'rm -rf "$SNAPSHOT"' EXIT
copied=0
for path in "${FILES[@]}"; do
  if [[ -f "$path" ]]; then
    mkdir -p "$SNAPSHOT/$(dirname "$path")"
    cp -p "$path" "$SNAPSHOT/$path"
    copied=$((copied+1))
  fi
done
[[ "$copied" -gt 0 ]] || { echo "No generated files"; exit 0; }

for attempt in 1 2 3 4 5; do
  git fetch origin main
  git reset --hard origin/main
  git clean -fd
  for path in "${FILES[@]}"; do
    if [[ -f "$SNAPSHOT/$path" ]]; then
      mkdir -p "$(dirname "$path")"
      cp -p "$SNAPSHOT/$path" "$path"
    fi
  done
  git add -- "${FILES[@]}"
  git diff --cached --quiet && { echo "No generated output changes"; exit 0; }
  git commit -m "$MESSAGE"
  git push origin HEAD:main && exit 0
  echo "Push race on attempt $attempt; retrying"
done
echo "Unable to publish after 5 attempts" >&2
exit 1
