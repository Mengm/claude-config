---
name: unity-artifact-inspect
description: 查询 Unity project 中 asset 的引用关系、Library artifact 文件、用 binary2text 转出可读文本。触发场景 (1) "xxx.mat / xxx.prefab 引用了哪些资源" / "依赖关系" (2) "看 xxx.fbx import 后是什么样" / "binary2text 这个资源" (3) "这个 Library 文件是哪个 asset" / "反查 artifact" (4) 用户提供 .meta 文件、.mat/.prefab 文件、Library/Artifacts 路径、或 Unity project 根目录。即使没明确说 "binary2text"，只要意图是查 import 产物或资源引用都应触发。
---

# Unity Artifact Inspect

把 Unity project 的 asset 引用关系 / Library artifact 文件方便地查清楚。

**核心原则（实测验证）：**
- 引用关系优先从**源文件**（文本 YAML）提取，不依赖 artifact
- artifact 反查 guid **必须读 LMDB**（artifact 文件名不含 guid，纯字符串前缀匹配不可行）
- guid 索引必须覆盖 `Assets/` + `Packages/` + `Library/PackageCache/`
- 大项目（实测 492k .meta）用单进程 awk 扫描 ≈ 5min；用 `-P N -I{}` 逐文件 spawn ≈ 100min+，**禁用**

## 何时触发

- 用户问某个资产（.mat / .prefab / .asset / .scene / .controller / .fbx 等）引用了哪些资源
- 用户想看某个资产 import 之后的 SerializedFile 内容（二进制 artifact → 文本）
- 用户想反查 Library 里某个文件是哪个 asset 生成的
- 用户提供 `.meta`、`Library/Artifacts/...` 路径、Unity project 根目录

## 前置约定

### Project 路径来源

skill 不持久化 project 路径。来源优先级：
1. 用户当前消息显式给出
2. 对话上下文最近一次确认过的 project 路径
3. 当前 shell cwd（若是 Unity project）
4. 都没有 → 反问

**判定是否 Unity project**：含 `Assets/` 子目录即可。不强求 `Library/`（refs 仅需 .meta 索引）。

### binary2text.exe 解析顺序

仅 inspect 动作需要。
1. `--bin2text <path>`
2. `UNITY_BINARY2TEXT` 环境变量
3. project 同盘扫描：
   - `C:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
   - `D:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
   - 同盘 `Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
4. fallback `f:/jnunity-2022-310/artifacts/Binary2Text/release_Win64_VS2019/binary2text.exe`
5. 找不到 → 报错并打印解析顺序

CLI：`binary2text inputbinaryfile [outputtextfile] [-detailed] [-largebinaryhashonly] [-hexfloat]`，skill 默认带 `-detailed`。

### 输出目录

固定 `<project>/Temp/unity-artifact-skill/`，首次使用 `mkdir -p`。
- `guid-index.tsv` — guid → asset 路径全量索引（Assets + Packages + PackageCache）
- `<asset-basename>.<artifactID-first8>.txt` — binary2text 输出

## 三个动作

### 1. refs — 查 asset 引用了哪些资源 ⭐最常用

**输入：** asset 路径（绝对或相对 project 根）或 .meta 路径

**实现路径分两种：**

#### A. 文本 YAML 资产（.mat / .prefab / .asset / .scene / .controller / .anim 等）

直接 grep 源文件，**不需要 artifact 也不需要 binary2text**。

```bash
SELF_GUID=$(awk '/^guid: /{print $2; exit}' "$ASSET.meta")
grep -oE 'guid: [0-9a-f]{32}' "$ASSET" | awk '{print $2}' | sort -u | grep -v "^$SELF_GUID$"
```

判断是否文本 YAML：`head -1 "$ASSET"` 是否以 `%YAML` 开头。

#### B. 二进制资产（.fbx / .png / .tga / .wav / 等）

先用 inspect 转成文本再 grep：

```bash
# binary2text 转出 .txt
# 然后：
grep -oE 'Guid [0-9a-f]{32}' "$txt" | awk '{print $2}' | sort -u
```

#### 路径反查

每个 guid 用 `guid-index.tsv` 反查 asset 路径，分类：
- 命中 `Assets/` → 工程资产
- 命中 `Packages/` 或 `Library/PackageCache/` → 包资产
- 前 8 字符全 0 → `<builtin>`
- 都未命中 → `<not found — 可能是已删除资产或 Library 残留引用>`

### 2. inspect — asset → artifact 文本（二进制资产用）

**输入：** asset 路径 或 GUID

**步骤：**
1. asset 路径 → 读 `.meta` 拿 guid（32 hex）
2. 找 artifact 文件：
   - **正确方法**：读 `Library/SourceAssetDB` 和 `Library/ArtifactDB`（LMDB），查 guid 对应的当前 ArtifactID。需要 `mdb_dump` 或 `python -m lmdb`，**第一版未实现**
   - **当前 fallback**：在 `Library/Artifacts/*/` 下用 `grep -rl` 搜包含该 guid 字节序列的 artifact 文件（慢但可行）
3. 取目录下最新 mtime 的命中文件
4. `binary2text.exe <artifact> <Temp/.../<name>.<id8>.txt> -detailed`
5. 返回 .txt 路径 + 头 50 行预览

**已知限制：**
- Unity 2022 的 ArtifactID 是独立 hash，**不是 guid+importer hash 拼接**。文件名前缀匹配 guid 的策略**不工作**
- 必须 LMDB 直读才能精确判定 current artifact，否则只能 grep 全 Library/Artifacts

### 3. whose — artifact → asset

**输入：** `Library/Artifacts/<2>/<rest>` 文件路径

**步骤：**
1. 读 artifact 文件，提取其中所有 `guid: <32hex>` 出现序列
2. 第一个出现的 guid 大概率就是 "self guid"（按 SerializedFile 约定，文件头部 ExternalReferences 之前会有 main object 信息）
3. 用 `guid-index.tsv` 反查路径

**更稳的方法（未实现）：** 读 ArtifactDB 的 reverse mapping。

## 实现脚本

skill 目录下提供两个可直接执行的脚本，调用方式见下面"用法示例"。

### scripts/build-guid-index.sh

```bash
PROJ="$1"  # Unity project 根
CACHE="$PROJ/Temp/unity-artifact-skill/guid-index.tsv"
mkdir -p "$(dirname "$CACHE")"
cd "$PROJ" || exit 1

# 扫 Assets / Packages / Library/PackageCache 三个位置
# 单进程 awk，避免逐文件 spawn 开销
DIRS=()
[ -d Assets ] && DIRS+=(Assets)
[ -d Packages ] && DIRS+=(Packages)
[ -d Library/PackageCache ] && DIRS+=(Library/PackageCache)

find "${DIRS[@]}" -name '*.meta' -type f -print0 2>/dev/null \
  | xargs -0 awk 'FNR==1{file=FILENAME; sub(/\.meta$/,"",file)} /^guid: /{print $2"\t"file; nextfile}' \
  > "$CACHE"

echo "Index: $CACHE ($(wc -l < "$CACHE") entries)"
```

### scripts/refs.sh

```bash
PROJ="$1"
ASSET="$2"  # asset 路径（绝对或相对 project）
CACHE="$PROJ/Temp/unity-artifact-skill/guid-index.tsv"

# 路径规范化
case "$ASSET" in
  /*|[A-Za-z]:*) ABS="$ASSET" ;;
  *) ABS="$PROJ/$ASSET" ;;
esac

# 索引就绪？
if [ ! -f "$CACHE" ] || [ -z "$(find "$CACHE" -mtime -1 2>/dev/null)" ]; then
  bash "$(dirname "$0")/build-guid-index.sh" "$PROJ"
fi

# self guid
SELF=$(awk '/^guid: /{print $2; exit}' "$ABS.meta" 2>/dev/null)
[ -z "$SELF" ] && { echo "ERROR: no .meta for $ABS"; exit 1; }

# 文本 YAML 直接 grep；二进制提示走 inspect
if head -1 "$ABS" 2>/dev/null | grep -q '^%YAML'; then
  GUIDS=$(grep -oE 'guid: [0-9a-f]{32}' "$ABS" | awk '{print $2}' | sort -u | grep -v "^$SELF$")
else
  echo "ERROR: $ABS 不是文本 YAML，先用 inspect 转出 .txt 再 grep（未自动化）"
  exit 2
fi

# 反查
COUNT=$(echo "$GUIDS" | grep -c .)
echo "=== $ASSET 引用 $COUNT 个外部 guid ==="
for g in $GUIDS; do
  if echo "$g" | grep -qE '^0{7}'; then
    printf "  %s  ->  <builtin>\n" "$g"
  else
    HIT=$(awk -F'\t' -v g="$g" '$1==g{print $2; exit}' "$CACHE")
    if [ -n "$HIT" ]; then
      printf "  %s  ->  %s\n" "$g" "$HIT"
    else
      printf "  %s  ->  <not found>\n" "$g"
    fi
  fi
done
```

## 用法示例

Claude 在响应触发时，应直接调用脚本，不要现写一次性命令：

```bash
# 查引用
bash ~/.claude/skills/unity-artifact-inspect/scripts/refs.sh \
  "F:/Perforce/Project-T3-baiyuan/client" \
  "Assets/ResTemp/Environment/Rock/Materials/M_Rock_AlienStar_Forest_03a.mat"

# 单独建/刷新索引
bash ~/.claude/skills/unity-artifact-inspect/scripts/build-guid-index.sh \
  "F:/Perforce/Project-T3-baiyuan/client"
```

## 已知问题与降级

| 情况 | 行为 |
|---|---|
| 大项目首次索引慢（实测 49 万 .meta = 5min） | 告诉用户首次会慢，后续命中缓存秒级 |
| 引用 guid 在 Assets/Packages 都查不到 | 标 `<not found>` — 通常是已删除资产或残留引用 |
| asset 是二进制 (.fbx / .png) | 暂未自动化，建议先用 binary2text 手转，未来在 refs.sh 加分支 |
| ArtifactDB / SourceAssetDB 解析 | 第一版未做，留 `references/lmdb-schema.md` 锚点 |
| Unity Editor 正在运行该 project | .meta 扫描不受影响；LMDB 读会被阻塞 |
| binary2text 找不到 | 打印解析顺序，让用户传 `--bin2text` |

## 参考

- `references/library-layout.md` — Unity 2022 `Library/Artifacts/` 结构
- `references/binary2text-output.md` — binary2text 输出格式 + guid 提取正则
- `references/lmdb-schema.md` — SourceAssetDB / ArtifactDB LMDB schema 锚点
- `scripts/build-guid-index.sh` — 全量 guid 索引构建
- `scripts/refs.sh` — refs 主入口
