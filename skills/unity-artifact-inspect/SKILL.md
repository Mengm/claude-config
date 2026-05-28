---
name: unity-artifact-inspect
description: 查询 Unity project 中 asset 的引用关系、Library artifact 文件、用 binary2text 转出可读文本。触发场景 (1) "xxx.mat / xxx.prefab / xxx.fbx 引用了哪些资源" / "依赖关系" (2) "看 xxx.fbx import 后是什么样" / "binary2text 这个资源" (3) "这个 Library 文件是哪个 asset" / "反查 artifact" (4) 用户提供 .meta、.mat/.prefab/.fbx/.png 文件、Library/Artifacts 路径、或 Unity project 根目录。即使没明确说 "binary2text"，只要意图是查 import 产物或资源引用都应触发。
---

# Unity Artifact Inspect

把 Unity project 的 asset 引用关系 / Library import 产物方便地查清楚。**无需打开 Unity Editor。**

**能力总览：**
| 动作 | 输入 | 脚本 |
|---|---|---|
| **refs** 查引用 | 任意 asset（文本或二进制）或 guid | `scripts/refs.sh` |
| **inspect** 转可读文本 | 任意 asset 或 guid | `scripts/inspect.sh` |
| **resolve** guid→磁盘 artifact | asset 或 guid | `scripts/resolve-artifact.sh` |
| **whose** 反查 artifact→asset | Library/Artifacts 文件 | 见下文 |

**核心机制（全部对 Unity 2022.3 源码 + 真实项目验证）：**
- 文本 YAML 资产（.mat/.prefab/.asset/.scene…）→ 直接 grep 源文件提引用
- 二进制资产（.fbx/.png/.tga…）→ 读 LMDB ArtifactDB 找到磁盘 artifact → binary2text → 提引用
- guid↔asset 反查用 `guid-index.tsv`（覆盖 Assets+Packages+PackageCache）
- guid→磁盘 artifact 用 `unity_lmdb_dump.exe` 解析 LMDB（详见 `references/lmdb-schema.md`）

## 一次性准备：编译 unity_lmdb_dump.exe

inspect / resolve / 二进制 refs 依赖一个本地小工具（从 Unity 自带 LMDB 源码编译，零外部依赖）：

```cmd
bin\build-mdb_dump.bat
```

产物 `bin/unity_lmdb_dump.exe`。需要 MSVC（脚本自动 source vcvars64.bat，路径在脚本顶部，按需改）。
**只需编译一次**，之后所有项目复用。已编译则跳过。

## 前置约定

### Project 路径
不持久化。优先级：用户当前消息显式给出 > 对话上下文最近确认 > shell cwd（若是 Unity project）> 反问。
判定 Unity project：含 `Assets/`。refs 文本路径仅需 .meta；二进制/inspect 需要 `Library/ArtifactDB`。

### binary2text.exe 解析顺序（inspect 用）
1. `--bin2text <path>` 2. `UNITY_BINARY2TEXT` 3. project 同盘 Unity Hub 安装 4. fallback `f:/jnunity-2022-310/artifacts/Binary2Text/release_Win64_VS2019/binary2text.exe`

### 输出目录
固定 `<project>/Temp/unity-artifact-skill/`：
- `guid-index.tsv` — guid→asset 全量索引
- `CurrentRevisions.hexdump` / `ArtifactMetaInfo.hexdump` — LMDB dump 缓存（24h）
- `<name>.<contentHash8>.txt` — binary2text 输出

## 用法

```bash
SK=~/.claude/skills/unity-artifact-inspect/scripts
PROJ="F:/Perforce/Project-T3-baiyuan/client"

# 查引用（自动识别文本/二进制；可传 asset 路径或 32 位 guid）
bash "$SK/refs.sh" "$PROJ" "Assets/.../M_Rock.mat"
bash "$SK/refs.sh" "$PROJ" "3994342fc8249c44ea48d18eb68a03fe"   # 一个 .fbx 的 guid

# 转可读文本（返回 .txt 路径），二进制资产也行
bash "$SK/inspect.sh" "$PROJ" "Assets/.../model.fbx"

# guid -> 磁盘 artifact 文件
bash "$SK/resolve-artifact.sh" "$PROJ" "<guid 或 asset 路径>"

# 刷新 guid 索引
bash "$SK/build-guid-index.sh" "$PROJ"
```

## 各动作说明

### refs — 查 asset 引用 ⭐
- 文本 YAML：grep `guid:` 提取 → 反查路径
- 二进制 / 纯 guid：`inspect.sh` 转文本 → grep `GUID:`/`guid:`（binary2text 用大写 `GUID:`）→ 反查
- 输出每个引用 guid → asset 路径，分类 `<builtin>` / `<not found>`（已删除或残留引用）

### inspect — asset → binary2text 文本
经 `resolve-artifact.sh` 找到磁盘 artifact（不靠猜文件名），再 `binary2text -detailed` 转文本。
一个 asset 可能产出多个 artifact 文件（主数据 + meta），每个都转。

### resolve-artifact — guid → 磁盘 artifact 文件
完整 LMDB 链路（详见 `references/lmdb-schema.md`）：
```
.meta guid --nibble-swap--> LMDB guid
  --CurrentRevisions--> 当前 artifactID
  --ArtifactIDToArtifactMetaInfo--> producedFiles[].contentHash
  --> Library/Artifacts/<ch[0:2]>/<contentHash>
```
**磁盘文件名 = contentHash，不是 artifactID 也不是 guid。**

### whose — artifact 文件 → asset
1. binary2text 该 artifact 文件 → 文本里第一段 self 信息 / NativeFormatImporter
2. 或用 `unity_lmdb_dump.exe SourceAssetDB GuidToPath` 反查：value=assetPath，key=guid(nibble-swap 回 .meta 形式)
GuidToPath 的 value 直接是 ASCII assetPath，最稳。

## 性能（实测 Project-T3, 49 万资产）
- guid-index.tsv 首次构建：单进程 awk ≈ 5min（**禁用** `xargs -P -I{}` 逐文件 spawn，≈100min）
- LMDB dump：CurrentRevisions 2s / ArtifactMetaInfo（大）≈ 27s，缓存 24h，后续秒级
- resolve / inspect 命中缓存后秒级

## 已知问题与降级
| 情况 | 行为 |
|---|---|
| unity_lmdb_dump.exe 未编译 | 提示运行 `bin/build-mdb_dump.bat` |
| guid 在 CurrentRevisions 无记录 | "asset 未 import / Library stale" |
| LMDB 指向的 contentHash 磁盘不存在 | resolve 只输出磁盘真实存在的；可能已 GC |
| 引用 guid 在 Assets/Packages 查不到 | 标 `<not found>`（已删除或残留引用）|
| 前 8 位全 0 的 guid | `<builtin>`（Unity 内置资源）|
| Editor 正在运行 | LMDB 以 MDB_NOLOCK 只读，不受影响 |

## 文件结构
```
unity-artifact-inspect/
├── SKILL.md
├── bin/
│   ├── unity_lmdb_dump.c       # LMDB sub-DB dumper 源码
│   ├── build-mdb_dump.bat      # MSVC 编译脚本
│   └── unity_lmdb_dump.exe     # 编译产物（首次运行 .bat 生成）
├── scripts/
│   ├── build-guid-index.sh     # guid→asset 全量索引
│   ├── refs.sh                 # 查引用（主入口）
│   ├── inspect.sh              # asset→binary2text 文本
│   └── resolve-artifact.sh     # guid→磁盘 artifact（LMDB）
└── references/
    ├── library-layout.md       # Library/Artifacts 结构
    ├── binary2text-output.md   # binary2text 输出格式 + guid 正则
    └── lmdb-schema.md          # ★ 完整 LMDB schema + guid→artifact 链路
```
