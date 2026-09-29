#!/usr/bin/env bash
# Auto-deploy the Lab cockpit: fast-forward the dev branch and restart mex-lab
# only when the remote moved. Safe (ff-only). Wired via mex-lab-autopull.timer.
set -euo pipefail
REPO=/root/mex-journal
BRANCH=claude/middleware-setup-guide-afhvtk
cd "$REPO"
git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "autopull: $LOCAL -> $REMOTE"
  git checkout -q "$BRANCH"
  git pull -q --ff-only origin "$BRANCH"
  systemctl restart mex-lab
  echo "autopull: mex-lab restarted"
else
  echo "autopull: already up to date ($LOCAL)"
fi
