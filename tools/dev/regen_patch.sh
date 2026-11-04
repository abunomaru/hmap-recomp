#!/usr/bin/env sh
# Regenerates engine-patches/<NAME>.patch from the engine's current working tree.
#   1. edit files in extern/wiiparty-recomp (with all patches applied, e.g. after any hmap.py command)
#   2. sh tools/dev/regen_patch.sh 0013-aurora-video-backend.patch
# The patch becomes "what this file set looks like now" minus "patches before it". Files it
# touches must not be touched by later patches (they would be rebased by hand).
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=$1
ENGINE="$ROOT/extern/wiiparty-recomp"
PATCH="$ROOT/engine-patches/$NAME"
[ -f "$PATCH" ] || { echo "no such patch: $PATCH" >&2; exit 1; }
FILES=$(sed -n 's|^+++ b/||p' "$PATCH")
TMP=$(mktemp -d)
for f in $FILES; do mkdir -p "$TMP/new/$(dirname "$f")"; [ -f "$ENGINE/$f" ] && cp "$ENGINE/$f" "$TMP/new/$f"; done
cd "$ENGINE"
git checkout -q -- .
git clean -fdq engine third_party
for p in "$ROOT"/engine-patches/*.patch; do
    [ "$p" = "$PATCH" ] && break
    git apply "$p"
done
git add -A >/dev/null
for f in $FILES; do [ -f "$TMP/new/$f" ] && { mkdir -p "$(dirname "$f")"; cp "$TMP/new/$f" "$f"; }; done
git add -N . >/dev/null 2>&1 || true
git diff --cached --quiet || true
git diff -- $FILES > "$PATCH"
git reset -q
git checkout -q -- .
git clean -fdq engine third_party
rm -f "$(git rev-parse --git-path hmap-engine-patches.stamp)"
rm -rf "$TMP"
echo "regenerated $PATCH; run any hmap.py command to re-apply the series"
