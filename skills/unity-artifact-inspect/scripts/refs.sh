#!/usr/bin/env bash
# 查 Unity asset 引用的所有外部 guid，反查到 asset 路径。
# 用法: bash refs.sh <project-root> <asset-path-or-guid>
#
# 两条路径：
#   A. 文本 YAML 资产 (.mat/.prefab/.asset/.scene/...) -> 直接 grep 源文件
#   B. 二进制资产 (.fbx/.png/.tga/...) 或纯 guid 输入 -> 经 LMDB 找 artifact
#      -> binary2text -> 从文本提取 Guid 引用
# guid -> 资产路径 反查使用 guid-index.tsv（覆盖 Assets+Packages+PackageCache）

set -u

PROJ="${1:-}"
INPUT="${2:-}"
if [ -z "$PROJ" ] || [ -z "$INPUT" ]; then
  echo "Usage: $0 <project-root> <asset-path-or-guid>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="$PROJ/Temp/unity-artifact-skill/guid-index.tsv"

# --- ensure guid index (covers Assets+Packages+PackageCache) ---
if [ ! -f "$CACHE" ] || [ -z "$(find "$CACHE" -mmin -1440 2>/dev/null)" ]; then
  echo "Building guid index (first run can take minutes on large projects)..." >&2
  bash "$SCRIPT_DIR/build-guid-index.sh" "$PROJ" >/dev/null || exit 1
fi

lookup_guid() {  # $1 = guid -> prints path or marker
  local g="$1"
  if echo "$g" | grep -qE '^0{7}'; then echo "<builtin>"; return; fi
  local hit
  hit=$(awk -F'\t' -v g="$g" '$1==g{print $2; exit}' "$CACHE")
  if [ -n "$hit" ]; then echo "$hit"; else echo "<not found>"; fi
}

# --- determine input kind ---
IS_GUID=0
[[ "$INPUT" =~ ^[0-9a-fA-F]{32}$ ]] && IS_GUID=1

if [ "$IS_GUID" = "1" ]; then
  ABS=""; REL="$INPUT"; SELF=$(echo "$INPUT" | tr 'A-F' 'a-f')
else
  case "$INPUT" in
    /*|[A-Za-z]:*) ABS="$INPUT" ;;
    *) ABS="$PROJ/$INPUT" ;;
  esac
  case "$ABS" in *.meta) ABS="${ABS%.meta}" ;; esac
  REL="${ABS#"$PROJ/"}"
  [ ! -f "$ABS" ] && { echo "ERROR: asset not found: $ABS" >&2; exit 1; }
  SELF=$(awk '/^guid: /{print $2; exit}' "$ABS.meta" 2>/dev/null)
fi

# --- get GUID list from either YAML source or binary2text dump ---
TXTSRC=""
if [ "$IS_GUID" = "0" ] && head -c 5 "$ABS" 2>/dev/null | grep -q '^%YAML'; then
  TXTSRC="$ABS"
  GUIDS=$(grep -oE 'guid: [0-9a-f]{32}' "$TXTSRC" | awk '{print $2}' | sort -u)
else
  # binary asset or pure guid: resolve artifact + binary2text
  echo "Binary/opaque asset: resolving via LMDB ArtifactDB..." >&2
  mapfile -t TXTS < <(bash "$SCRIPT_DIR/inspect.sh" "$PROJ" "$INPUT" 2>/dev/null)
  if [ "${#TXTS[@]}" = "0" ]; then
    echo "ERROR: could not inspect '$INPUT' (no artifact / binary2text failed)" >&2
    exit 3
  fi
  # binary2text emits "GUID: <hex>" (External References) and "guid: <hex>"; accept both
  GUIDS=$(grep -hoiE 'guid:? [0-9a-f]{32}' "${TXTS[@]}" 2>/dev/null \
            | grep -oE '[0-9a-f]{32}' | sort -u)
fi

# drop self
[ -n "$SELF" ] && GUIDS=$(printf '%s\n' "$GUIDS" | grep -v "^$SELF$" || true)

if [ -z "$GUIDS" ]; then
  echo "$REL 没有引用其他 asset"
  exit 0
fi

COUNT=$(printf '%s\n' "$GUIDS" | grep -c .)
echo "=== $REL 引用 $COUNT 个外部 guid ==="
[ -n "$SELF" ] && echo "(self guid: $SELF)"

FOUND=0; BUILTIN=0; MISSING=0
for g in $GUIDS; do
  res=$(lookup_guid "$g")
  printf "  %s  ->  %s\n" "$g" "$res"
  case "$res" in
    "<builtin>") BUILTIN=$((BUILTIN+1)) ;;
    "<not found>") MISSING=$((MISSING+1)) ;;
    *) FOUND=$((FOUND+1)) ;;
  esac
done

echo ""
echo "Summary: $FOUND resolved / $BUILTIN builtin / $MISSING not found"
