#!/usr/bin/env bash
# Resolve a Unity asset GUID to its current on-disk Library artifact file(s),
# by reading the LMDB ArtifactDB. No Unity Editor required.
#
# Usage: bash resolve-artifact.sh <project-root> <guid-or-asset-path>
#
# Output: one line per produced artifact file
#   <contentHash>  <Library/Artifacts/xx/contentHash>  <bytes>
#
# CHAIN (all verified against Unity 2022.3 source + live Project-T3):
#   .meta guid
#     --[nibble-swap each byte]-->  LMDB guid bytes
#     --[CurrentRevisions: value[0:16]==guid, artifactID = value last 16 bytes]-->  artifactID
#     --[ArtifactIDToArtifactMetaInfo[artifactID] -> ArtifactMetaInfo blob]-->
#        producedFiles[].contentHash  (we locate them by scanning 16-byte windows
#                                      that map to an existing file on disk)
#     --> Library/Artifacts/<ch[0:2]>/<contentHash>
#
# Disk artifact filename = Hash128ToString(producedFile.contentHash), NOT the artifactID.
# (Runtime/.../ArtifactPath.cpp FilePathFromHash + ArtifactInfo.cpp GetHashedContentPath)

set -u

PROJ="${1:-}"
INPUT="${2:-}"
if [ -z "$PROJ" ] || [ -z "$INPUT" ]; then
  echo "Usage: $0 <project-root> <guid-or-asset-path>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP="$SCRIPT_DIR/../bin/unity_lmdb_dump.exe"
ARTIFACTDB="$PROJ/Library/ArtifactDB"
SRCDB="$PROJ/Library/SourceAssetDB"
CACHE_DIR="$PROJ/Temp/unity-artifact-skill"
mkdir -p "$CACHE_DIR"

if [ ! -f "$DUMP" ]; then
  echo "ERROR: unity_lmdb_dump.exe not found. Build it: bin/build-mdb_dump.bat" >&2
  exit 1
fi
if [ ! -f "$ARTIFACTDB" ]; then
  echo "ERROR: $ARTIFACTDB not found (project never imported?)" >&2
  exit 1
fi

# --- resolve INPUT to a 32-hex .meta guid ---
if [[ "$INPUT" =~ ^[0-9a-fA-F]{32}$ ]]; then
  GMETA=$(echo "$INPUT" | tr 'A-F' 'a-f')
else
  case "$INPUT" in
    /*|[A-Za-z]:*) ABS="$INPUT" ;;
    *) ABS="$PROJ/$INPUT" ;;
  esac
  case "$ABS" in *.meta) ABS="${ABS%.meta}" ;; esac
  if [ ! -f "$ABS.meta" ]; then
    echo "ERROR: no .meta for $ABS" >&2
    exit 1
  fi
  GMETA=$(awk '/^guid: /{print $2; exit}' "$ABS.meta")
fi

# --- nibble-swap each byte: .meta hex <-> LMDB memory bytes ---
swap_nibbles() {
  local s=$1 out="" i
  for ((i=0; i<${#s}; i+=2)); do out="$out${s:$((i+1)):1}${s:$i:1}"; done
  echo "$out"
}
GSWAP=$(swap_nibbles "$GMETA")

# --- build/refresh dumps (24h cache) ---
CR="$CACHE_DIR/CurrentRevisions.hexdump"
MI="$CACHE_DIR/ArtifactMetaInfo.hexdump"
need() { [ ! -f "$1" ] || [ -z "$(find "$1" -mmin -1440 2>/dev/null)" ]; }
if need "$CR"; then
  echo "Dumping CurrentRevisions..." >&2
  "$DUMP" "$ARTIFACTDB" CurrentRevisions > "$CR" 2>/dev/null || { echo "dump CurrentRevisions failed" >&2; exit 1; }
fi
if need "$MI"; then
  echo "Dumping ArtifactIDToArtifactMetaInfo (large, ~30s)..." >&2
  "$DUMP" "$ARTIFACTDB" ArtifactIDToArtifactMetaInfo > "$MI" 2>/dev/null || { echo "dump ArtifactMetaInfo failed" >&2; exit 1; }
fi

# --- Step 1: guid -> current artifactID (CurrentRevisions) ---
AID=$(awk -v g="$GSWAP" '
  /^V /{ v=substr($0,3); if (substr(v,1,32)==g) { print substr(v, length(v)-31, 32); exit } }
' "$CR")

if [ -z "$AID" ]; then
  echo "NOT FOUND: guid $GMETA has no current revision (asset not imported, or Library stale)" >&2
  exit 3
fi

# --- Step 2: artifactID -> ArtifactMetaInfo value ---
VAL=$(awk -v k="$AID" '
  /^K /{ key=$2; getline; if (key==k) { print substr($0,3); exit } }
' "$MI")

if [ -z "$VAL" ]; then
  echo "NOT FOUND: artifactID $AID has no ArtifactMetaInfo entry" >&2
  exit 3
fi

# --- Step 3: scan 16-byte windows; emit those that exist on disk ---
# (producedFiles[].contentHash; robust against blob-offset layout drift)
nbytes=$(( ${#VAL} / 2 ))
found=0
declare -A seen
for ((b=0; b<=nbytes-16; b++)); do
  win="${VAL:$((b*2)):32}"
  [ -n "${seen[$win]:-}" ] && continue
  seen[$win]=1
  P="$PROJ/Library/Artifacts/${win:0:2}/$win"
  if [ -f "$P" ]; then
    sz=$(stat -c%s "$P" 2>/dev/null || echo "?")
    printf '%s\t%s\t%s\n' "$win" "$P" "$sz"
    found=$((found+1))
  fi
done

if [ "$found" = "0" ]; then
  echo "NOT FOUND: artifactID $AID resolved but no produced file exists on disk (GC'd?)" >&2
  exit 3
fi
exit 0
