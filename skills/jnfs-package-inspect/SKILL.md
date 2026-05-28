---
name: jnfs-package-inspect
description: 解析 JN 引擎 JNFS 包体（.idx/.data）配合 build manifest JSON（含 AssetPath/Hash/InternalPath/PackageTag/FileSize），生成按扩展名 + SVT/Streaming 专项分桶的资源占用报告（Markdown + Excel + 飞书在线表格），并支持精确 AssetPath 查询某个资产是否入包、落在哪个 JNFS 包文件。触发场景：用户提供 Game_Data 目录 + manifest JSON、问"哪些资源占了包体多少"、问"xxx.prefab 在不在包里"、问"SVT/streaming 数据有多大"、需要资源类型分布报告或入包 audit。即使没明确说 JNFS，只要意图是分析 JN 引擎 build 产物（含 .idx/.data 对、`StandaloneWindows64_xxx_full.json` 这类 manifest）的资源构成或入包情况都应触发。
---

# JNFS Package Inspect

解析 JN 引擎 JNFS 包体 + build manifest JSON，做两件事：

1. **资源类型占用报告** —— 按扩展名 + SVT/Streaming 专项分桶，生成 Markdown + Excel，默认导入为飞书在线表格
2. **入包查询** —— 精确 AssetPath 查询某资产是否打进了包，落在哪个 `.data` 包文件，hash 是多少

## When to use this skill

- 用户提供 `Game_Data` 目录（含 `.idx`/`.data` JNFS 包对）+ build manifest JSON
- 用户问"包体里 xxx 类资源多大 / 多少个"、"哪些类型最占体积"
- 用户问"`Assets/Res/xxx/yyy.prefab` 在不在包里"、"这资产入包没"
- 用户需要 SVT/streaming 数据占比、按 PackageTag (base/gameplay) 拆分
- 用户给一个 manifest 想看它声称的资产是否真在 JNFS 里（cross-check Hash → DataEntry）

## Core data model

JNFS 包体的 FileEntry 只存 `pathHash (U64 BE)`，**单向不可逆**——拿不回原始 AssetPath。所以这个 skill 的核心思路是把 manifest JSON 当作权威路径表：

```
manifest.AssetPath  ──(还原)──>  人类可读的 Unity 资源路径
manifest.Hash       ─────┐
                          │ MD5 (32 hex)
JNFS DataEntry.contentHash┘  ── join key, 双方一致
JNFS FileEntry.contentHash   ── 同一个 hash, 多个 FileEntry 可指向同一 DataEntry (去重)
```

**重要不变量**：manifest 总条目数 == JNFS 所有 .idx 的 file_entry 总数（去重前）。验证时拿这个数对一下，对得上说明 manifest 完整。

## Inputs

| 输入 | 必选 | 说明 |
|---|---|---|
| `manifest.json` | 是 | build manifest JSON 数组，每项含 `AssetPath`、`Hash`、`InternalPath`、`PackageTag`、`FileSize`。例：`StandaloneWindows64_common_full.json` |
| `Game_Data/...` | 否 | JNFS 包体根目录（递归找 `*.idx`）。提供后会做 manifest Hash ↔ JNFS DataEntry 的 cross-check，并把每个资产定位到具体 `.data` 包文件 |

## Workflow

### Mode 1：资源类型占用报告（默认）

```bash
python scripts/jnfs_inspect.py report <manifest.json> \
    [--game-data <Game_Data根目录>] \
    [-o <输出目录>] \
    [--no-xlsx]
```

输出文件（默认 `JnfsReport/`）：

| 文件 | 内容 |
|---|---|
| `report.md` | 总览 + PackageTag 分布 + 特殊分桶 + SVT 纹理集明细 + 扩展名分布 + 缺失审计 |
| `report.json` | 结构化原始报告（用于二次分析） |
| `report.xlsx` | 多 sheet：Overview / ByPackageTag / SpecialBuckets / SVTSets / ByExtension / AllEntries |

**分桶规则**：

特殊分桶（按 InternalPath 优先匹配）：
- `svt` —— Granite Streaming Virtual Texture (`svt/<guid>.gts`、`svt/<guid>-<hash>.gtp`)
- `streaming` / `entity-scenes` / `audio` / `video` / `addressable` / `scene-streaming`

特殊分桶之外按扩展名（`.fbx` / `.prefab` / `.mat` / `.png` / `.asset` / `.shader` / ...）。

SVT 还会按 32-char texture-set GUID 做二级分桶（每个 set 多少 .gts / 多少 .gtp / 总大小），用来定位 SVT 体积大头。

### Mode 2：入包查询（精确 AssetPath）

单个查询：

```bash
python scripts/jnfs_inspect.py lookup <manifest.json> \
    --asset-path "Assets/Res/GUI/StartUp/Start.prefab" \
    [--asset-path "Assets/Res/Other.mat"] \
    [--game-data <Game_Data根目录>] \
    [--json]
```

批量查询（一行一个 AssetPath，`#` 开头视为注释）：

```bash
python scripts/jnfs_inspect.py lookup <manifest.json> \
    --from-file <asset_list.txt> \
    --game-data <Game_Data根目录>
```

输出格式（人读）：

```
[IN ] Assets/Res/GUI/StartUp/Start.prefab
      hash=d77f6da410f736a9fe3aea94f94c64ab  size=10,807  pkg_tag=base  ext=.prefab  special=-
      jnfs=common/base/data.0.idx
[OUT] Assets/Res/Foo/Bar.prefab   (AssetPath not in manifest)
```

退出码：所有 AssetPath 都在包里返回 0；任意一个不在返回 1（方便 CI / 脚本批量校验）。

`--json` 切换为机器可读输出。

## 飞书表格上传（默认）

报告生成后，默认把 `report.xlsx` 导入为飞书在线电子表格：

```powershell
python scripts/jnfs_inspect.py report <manifest> --game-data <Game_Data> -o <out>

Set-Location <out>
lark-cli drive +import --as user `
    --file ".\report.xlsx" `
    --type sheet `
    --name "JNFS Package Inspect <build-name> <YYYYMMDD>"
```

约束（沿用 `shader-variant-analyzer` 的飞书规则）：
- 类型固定 `sheet`（不是普通文件附件）
- `--as user` 让表格归属当前用户云空间
- `--file` 必须是当前工作目录内的相对路径，先 `cd` 到 output 目录再传 `.\report.xlsx`
- 命名带 build 标识 + 日期，便于多次跑后区分
- 用户明确说"不要飞书"/"只本地"/`--no-xlsx` 时跳过

## 命名约定

| 字段 | 来源 | 说明 |
|---|---|---|
| `AssetPath` | manifest | Unity 项目内的资产路径，部分流式资源（如 SVT）此字段为空 |
| `InternalPath` | manifest | JNFS 内部相对路径（一定有值） |
| `Hash` | manifest | 32-hex MD5，作为 join key |
| `PackageTag` | manifest | 业务分桶（base/gameplay/... 由打包流程定义） |
| `FileSize` | manifest | 单文件原始字节数（未压缩） |

## Examples

### 例 1：T3_shiwan PC 包体全览 + 飞书

```powershell
python scripts/jnfs_inspect.py report `
    "D:\ps5文档\StandaloneWindows64_common_full.json" `
    --game-data "C:\...\T3_shiwan\Game_Data\StreamingAssets\res" `
    -o "T3ShiwanReport"

Set-Location "T3ShiwanReport"
lark-cli drive +import --as user --file ".\report.xlsx" --type sheet `
    --name "T3 shiwan JNFS Inspect 20260528"
```

期望（基于 T3_shiwan v0.0.214）：总条目 153,509，SVT 22.31 GB（14 个 set，3,948 个 .gts/.gtp），FBX ~1.23 GB，Material ~10 MB。

### 例 2：审一批资产是否入包

```bash
cat > /tmp/wanted.txt <<EOF
Assets/Res/GUI/StartUp/Start.prefab
Assets/Res/GUI/StartUp/JNSettingInfo.json
Assets/Res/Foo/NotExist.prefab
EOF

python scripts/jnfs_inspect.py lookup \
    "D:/ps5文档/StandaloneWindows64_common_full.json" \
    --from-file /tmp/wanted.txt \
    --game-data "C:/.../T3_shiwan/Game_Data/StreamingAssets/res"
```

## Dependencies

- Python 3.7+
- `openpyxl` — Excel 导出（`pip install openpyxl`）。没装时自动跳过 xlsx，仍输出 md/json
- `lark-cli` — 飞书表格导入（按 `lark-shared` 完成 user 身份认证）

## Reference

- `references/jnfs-format.md` —— JNFS .idx / .data / JNTE 二进制格式细节，pathHash 单向性的成因，manifest 字段说明

## 与其他 skill 的配合

- 想看 Shader 变体本身的 keyword 使用 → `shader-variant-analyzer`
- 想做 GPU/渲染问题排查 → `renderdoc-analyze`
- 想看 Unity 项目里某资产的依赖图（不是入包性） → `unity-artifact-inspect`
