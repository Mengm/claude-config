#!/usr/bin/env bash
# 查 Unity asset 引用的所有外部 guid，反查到 asset 路径
# 用法: bash refs.sh <project-root> <asset-path>
#   asset-path 可以是相对 project 的路径或绝对路径，也可传 .meta

set -u

PROJ="${1:-}"
ASSET="${2:-}"

if [ -z "$PROJ" ] || [ -z "$ASSET" ]; then
  echo "Usage: $0 <project-root> <asset-path>" >&2
  exit 1
fi

# 规范化路径
case "$ASSET" in
  /*|[A-Za-z]:*) ABS="$ASSET" ;;
  *) ABS="$PROJ/$ASSET" ;;
esac

# .meta 后缀剥离（如果用户传了 .meta）
case "$ABS" in
  *.meta) ABS="${ABS%.meta}" ;;
esac

REL="${ABS#"$PROJ/"}"

if [ ! -f "$ABS" ]; then
  echo "ERROR: asset not found: $ABS" >&2
  exit 1
fi

CACHE="$PROJ/Temp/unity-artifact-skill/guid-index.tsv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 索引就绪？(不存在 或 比 24h 旧 都重建)
NEED_BUILD=0
if [ ! -f "$CACHE" ]; then
  NEED_BUILD=1
elif [ -z "$(find "$CACHE" -mmin -1440 2>/dev/null)" ]; then
  NEED_BUILD=1
fi

if [ "$NEED_BUILD" = "1" ]; then
  echo "Index missing or stale, rebuilding..." >&2
  bash "$SCRIPT_DIR/build-guid-index.sh" "$PROJ" >/dev/null || exit 1
fi

# self guid
SELF=""
if [ -f "$ABS.meta" ]; then
  SELF=$(awk '/^guid: /{print $2; exit}' "$ABS.meta")
fi
if [ -z "$SELF" ]; then
  echo "WARN: no .meta for $ABS, can't filter self-references" >&2
fi

# 判断文本 YAML
IS_YAML=0
if head -c 5 "$ABS" 2>/dev/null | grep -q '^%YAML'; then
  IS_YAML=1
fi

if [ "$IS_YAML" = "0" ]; then
  cat >&2 <<EOF
ERROR: $REL 不是文本 YAML (二进制资产)
请先用 binary2text.exe 转成 .txt:
  binary2text.exe <Library/Artifacts/xx/...> <out.txt> -detailed
然后对 out.txt 跑 grep -oE 'Guid [0-9a-f]{32}' 提取引用。
未来版本会在本脚本自动化此路径。
EOF
  exit 2
fi

# 提取引用 guid (去重、去 self)
if [ -n "$SELF" ]; then
  GUIDS=$(grep -oE 'guid: [0-9a-f]{32}' "$ABS" | awk '{print $2}' | sort -u | grep -v "^$SELF$" || true)
else
  GUIDS=$(grep -oE 'guid: [0-9a-f]{32}' "$ABS" | awk '{print $2}' | sort -u)
fi

if [ -z "$GUIDS" ]; then
  echo "$REL 没有引用其他 asset"
  exit 0
fi

COUNT=$(printf '%s\n' "$GUIDS" | grep -c .)
echo "=== $REL 引用 $COUNT 个外部 guid ==="
[ -n "$SELF" ] && echo "(self guid: $SELF)"

# 反查
FOUND=0
BUILTIN=0
MISSING=0
for g in $GUIDS; do
  if echo "$g" | grep -qE '^0{7}'; then
    printf "  %s  ->  <builtin>\n" "$g"
    BUILTIN=$((BUILTIN+1))
  else
    HIT=$(awk -F'\t' -v g="$g" '$1==g{print $2; exit}' "$CACHE")
    if [ -n "$HIT" ]; then
      printf "  %s  ->  %s\n" "$g" "$HIT"
      FOUND=$((FOUND+1))
    else
      printf "  %s  ->  <not found>\n" "$g"
      MISSING=$((MISSING+1))
    fi
  fi
done

echo ""
echo "Summary: $FOUND resolved / $BUILTIN builtin / $MISSING not found"
