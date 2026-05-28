#!/usr/bin/env bash
# Inspect a Unity asset's imported artifact: resolve guid -> on-disk artifact,
# then run binary2text to produce a readable text dump.
#
# Usage: bash inspect.sh <project-root> <guid-or-asset-path> [--bin2text <path>]
#
# Output: prints the .txt path(s) written under <project>/Temp/unity-artifact-skill/
# Works for ANY asset (native .mat/.prefab and binary .fbx/.png/.tga/...),
# because it goes through the LMDB ArtifactDB rather than guessing file names.

set -u

PROJ="${1:-}"
INPUT="${2:-}"
shift 2 2>/dev/null || true

BIN2TEXT_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --bin2text) BIN2TEXT_OVERRIDE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [ -z "$PROJ" ] || [ -z "$INPUT" ]; then
  echo "Usage: $0 <project-root> <guid-or-asset-path> [--bin2text <path>]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$PROJ/Temp/unity-artifact-skill"
mkdir -p "$OUT_DIR"

# --- locate binary2text.exe ---
find_bin2text() {
  [ -n "$BIN2TEXT_OVERRIDE" ] && { echo "$BIN2TEXT_OVERRIDE"; return; }
  [ -n "${UNITY_BINARY2TEXT:-}" ] && { echo "$UNITY_BINARY2TEXT"; return; }
  local drive d
  drive="${PROJ:0:2}"
  for d in \
    "/c/Program Files/Unity/Hub/Editor"/*/Editor/Data/Tools/binary2text.exe \
    "/d/Program Files/Unity/Hub/Editor"/*/Editor/Data/Tools/binary2text.exe \
    "${drive}/Unity/Hub/Editor"/*/Editor/Data/Tools/binary2text.exe ; do
    [ -f "$d" ] && { echo "$d"; return; }
  done
  local fb="/f/jnunity-2022-310/artifacts/Binary2Text/release_Win64_VS2019/binary2text.exe"
  [ -f "$fb" ] && { echo "$fb"; return; }
  echo ""
}
B2T=$(find_bin2text)
if [ -z "$B2T" ] || [ ! -f "$B2T" ]; then
  echo "ERROR: binary2text.exe not found. Pass --bin2text <path> or set UNITY_BINARY2TEXT." >&2
  exit 1
fi

# basename for output naming
case "$INPUT" in
  *[/\\]*) BASE=$(basename "${INPUT%.meta}") ;;
  *)       BASE="$INPUT" ;;
esac

# --- resolve guid -> on-disk artifact(s) ---
mapfile -t ROWS < <(bash "$SCRIPT_DIR/resolve-artifact.sh" "$PROJ" "$INPUT" 2>/dev/null)
if [ "${#ROWS[@]}" = "0" ]; then
  echo "ERROR: could not resolve artifact for '$INPUT' (see resolve-artifact.sh)" >&2
  bash "$SCRIPT_DIR/resolve-artifact.sh" "$PROJ" "$INPUT" >/dev/null 2>&1 || true
  exit 3
fi

n=0
for row in "${ROWS[@]}"; do
  ch=$(echo "$row" | cut -f1)
  path=$(echo "$row" | cut -f2)
  [ -z "$path" ] && continue
  out="$OUT_DIR/${BASE}.${ch:0:8}.txt"
  if "$B2T" "$path" "$out" -detailed >/dev/null 2>&1; then
    echo "$out"
    n=$((n+1))
  else
    echo "WARN: binary2text failed on $path" >&2
  fi
done

[ "$n" = "0" ] && exit 3
exit 0
