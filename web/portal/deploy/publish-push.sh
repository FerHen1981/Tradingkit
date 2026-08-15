#!/usr/bin/env bash
# Commit and push the refreshed public snapshot so the sites rebuild.
#
# Called by mex-publish.service. Does nothing when the figures have not moved,
# so an unchanged day produces no commit and no deploy.
set -euo pipefail

REPO="${MEX_REPO:-/opt/mex}"
BRANCH="${MEX_PUBLISH_BRANCH:-main}"
FILES=(
  "web/sites/mex/src/data/public-stats.json"
)

cd "$REPO"

if git diff --quiet -- "${FILES[@]}"; then
  echo "public stats unchanged — nothing to publish"
  exit 0
fi

git add -- "${FILES[@]}"
git -c user.name="MEX publish" -c user.email="portal@mex-traders.com" \
    commit -m "chore(stats): refresh public snapshot"

# Retry on transient network failure; never leave a commit unpushed silently.
for delay in 0 2 4 8 16; do
  [ "$delay" -gt 0 ] && sleep "$delay"
  if git push origin "$BRANCH"; then
    echo "published"
    exit 0
  fi
  echo "push failed, retrying in $((delay * 2 == 0 ? 2 : delay * 2))s" >&2
done

echo "could not push the snapshot after 5 attempts" >&2
exit 1
