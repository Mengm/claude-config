#!/usr/bin/env bash
# 构建 Unity project 的 guid -> asset 路径全量索引
# 用法: bash build-guid-index.sh <project-root>
#
# 实测性能 (Project-T3, 492k .meta files):
#   单进程 awk: 5min19s ✓
#   xargs -P 8 -I{} sh -c grep: 100+ min ✗ (spawn 开销主导)
#
# 输出: <project>/Temp/unity-artifact-skill/guid-index.tsv
#   每行: <32-hex-guid>\t<asset-path-relative-to-project>

set -u

PROJ="${1:-}"
if [ -z "$PROJ" ]; then
  echo "Usage: $0 <unity-project-root>" >&2
  exit 1
fi

if [ ! -d "$PROJ/Assets" ]; then
  echo "ERROR: $PROJ has no Assets/ — not a Unity project?" >&2
  exit 1
fi

CACHE="$PROJ/Temp/unity-artifact-skill/guid-index.tsv"
mkdir -p "$(dirname "$CACHE")"

cd "$PROJ" || exit 1

DIRS=()
[ -d Assets ] && DIRS+=(Assets)
[ -d Packages ] && DIRS+=(Packages)
[ -d Library/PackageCache ] && DIRS+=(Library/PackageCache)

echo "Building guid index from: ${DIRS[*]}" >&2
echo "Output: $CACHE" >&2

START=$(date +%s)

find "${DIRS[@]}" -name '*.meta' -type f -print0 2>/dev/null \
  | xargs -0 awk 'FNR==1{file=FILENAME; sub(/\.meta$/,"",file)} /^guid: /{print $2"\t"file; nextfile}' \
  > "$CACHE"

END=$(date +%s)
LINES=$(wc -l < "$CACHE")
echo "Done: $LINES entries in $((END-START))s" >&2
echo "$CACHE"
