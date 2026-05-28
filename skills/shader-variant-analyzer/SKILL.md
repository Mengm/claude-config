---
name: shader-variant-analyzer
description: 解析 JNFS/UnityFS 包体中的 Shader 变体数据，扫描材质 keyword 使用情况，默认生成 Markdown + Excel 报告并将 Excel 导入为飞书在线表格。适用于用户提供 Game_Data 目录、问 shader 变体优化、问材质 keyword 分析、需要 shader 变体报告或需要上传飞书表格等场景。
---

# Shader Variant Analyzer

解析已打包的 JNFS 包体 + 标准 UnityFS (data.unity3d)，提取 Shader 对象的变体信息，结合材质 keyword 扫描，生成 P0-P5 分级优化建议。默认输出 Markdown + Excel 报告，并将 Excel 导入为飞书在线电子表格。

## When to use this skill

- 用户提供 Game_Data 目录（包含 .idx/.data JNFS 包或 data.unity3d）
- 用户问 shader 变体优化 / 变体爆炸 / shader 编译时间过长
- 用户问材质 keyword 使用分析 / 无用 keyword 清理
- 用户想了解 `multi_compile` vs `shader_feature` 优化策略
- 用户需要生成 shader 变体报告
- 用户需要把 shader 变体 Excel 报告上传或导入到飞书表格

## Workflow

### Phase 1: 包体 Shader 变体解析

使用 `scripts/shader_variant_analyzer.py` 解析包体中的 Shader 对象。

**数据源**：
1. **JNFS 包** (.idx + .data)：JN 引擎自定义归档格式，包含 JNTE 压缩容器
2. **UnityFS 包** (data.unity3d)：标准 Unity AssetBundle 格式

**解析流程**：
1. 遍历 Game_Data 目录，发现所有 `.idx`/`.data` 对和 `data.unity3d` 文件
2. 对每个包文件：解压 → 解析 SerializedFile → 提取 classID=48 (Shader) 对象
3. 对每个 Shader 对象：结构化解析 SerializedShader 二进制数据
4. 提取：shader name, keyword names, keyword flags, sub_shaders, passes, programs (variants)
5. 每个 `SerializedPlayerSubProgram` = 一个编译变体，记录其 keyword indices

**输出**：`List[ShaderInfo]`，每个包含 name, keywords, keyword_flags, sub_shaders（含 variant 计数）

### Phase 2: 材质 Keyword 扫描

扫描 Unity 项目 Assets/ 下所有 .mat 文件，提取启用的 shader keywords。

**两种 YAML 格式**：
- 新格式：`m_ValidKeywords` 数组（`- KEYWORD` 行）
- 旧格式：`m_ShaderKeywords: "KEYWORD1 KEYWORD2 ..."`

**输出**：`MaterialScanResult`，包含每个 keyword 被多少个材质使用、具体材质路径列表

### Phase 3: 报告生成

默认生成 Markdown 报告和 Excel 工作簿。不要把 Excel 当作可选附加物，除非用户明确说不需要 Excel 或使用 `--no-xlsx`。

| 文件 | 内容 |
|------|------|
| `summary.md` | Shader 总览表（按变体数排序）、Top 20 变体最多的 shader |
| `keyword_analysis.md` | 全局 keyword 频率、keyword ratio 分析（每个 keyword 在变体中的出现率） |
| `shader_details.md` | 每个 shader 的详细 keyword 列表（含 flag 类型标注） |
| `raw_data.json` | 结构化原始数据（用于后续分析） |
| `shader_pass_details.md` | 每个 shader/pass/stage 的变体与 keyword 组合详情 |
| `shader_variant_report.xlsx` | 飞书上传默认使用的 Excel 工作簿，包含概览、Shader-Pass、Keyword 组合、Keyword 分析、优化建议等 sheet |

### Phase 4: 优化建议生成（P0-P5 分级）

基于变体数据 + 材质 keyword 使用情况，生成 2 个优化报告：

| 文件 | 内容 |
|------|------|
| `optimization_recommendations.md` | P0-P5 分级优化建议，含具体 shader/keyword/影响变体数 |
| `material_keyword_usage.md` | 材质 keyword 使用统计、Top 50 最常用 keyword、孤儿 keyword |

### Phase 5: 默认上传飞书表格

默认将 `{output_dir}/shader_variant_report.xlsx` 导入为飞书在线电子表格，而不是只上传成普通附件。

执行规则：
- 使用 `lark-drive` 的 `drive +import` shortcut，目标类型固定为 `sheet`。
- 优先使用 `--as user`，让表格归属当前用户；没有指定 `--folder-token` 时导入到当前用户云空间根目录。
- `lark-cli drive +import` 要求 `--file` 是当前工作目录内的相对路径；先切换到输出目录，再传 `.\shader_variant_report.xlsx`。
- 导入名称优先使用包体/输出目录语义，例如 `T3_development Shader Variant Report 20260420`。
- 如果用户明确说“不上传飞书”“只本地生成”“不要 Excel”，按用户要求跳过对应步骤。
- 如果 CLI 因 sandbox、登录或 scope 权限失败，按 `lark-shared` 的最小授权流程处理；不要把 Excel 改成普通文件上传来绕过导入失败。

标准命令：

```powershell
python C:\workflow\skills\shader-variant-analyzer\scripts\shader_variant_analyzer.py `
  "<Game_Data路径>" `
  -o "<输出目录>"

Set-Location "<输出目录>"
lark-cli drive +import --as user `
  --file ".\shader_variant_report.xlsx" `
  --type sheet `
  --name "<报告名称>"
```

如需导入到指定飞书文件夹，在第二条命令追加：

```powershell
--folder-token <FOLDER_TOKEN>
```

## P0-P5 优化分级说明

### P0: `multi_compile` → `shader_feature` 候选

**判定条件**：
- keyword ratio ≈ 0.3-0.7（变体未被 strip，on/off 两版都存在）
- keyword 材质使用数 = 0 或极低
- 影响变体数 ≥ 阈值

**预期收益**：直接减半相关 keyword 的变体数量

**操作**：将 shader 源码中对应 keyword 从 `multi_compile` 改为 `shader_feature` 或 `shader_feature_local`

### P1: 从未使用的 Keyword（ratio = 0）

**判定条件**：
- keyword 在所有 pass/stage 中 ratio = 0（编译变体中从未出现 ON 状态）
- keyword 被 shader 声明但实际已被编译器 strip

**预期收益**：可从 shader 源码中安全移除声明，减少编译开销

**操作**：从 shader 源码中移除对应 keyword 的 `multi_compile` / `shader_feature` 声明

### P2: VFX Keyword 隔离

**判定条件**：
- 非 VFX shader（如 Environment/Lit, Character/*）中包含大量 `VFX_USE_*` keyword
- 这些 VFX keyword 大部分 ratio = 0

**预期收益**：减少 keyword 声明污染，降低编译矩阵复杂度

**操作**：VFX pass 使用 `shader_feature_local`，或拆为独立 subshader

### P3: T3Uber / PostProcessing 全 `multi_compile` 优化

**判定条件**：
- PostProcessing uber shader 全部 keyword 使用 `multi_compile`
- 导致变体组合爆炸（如 T3Uber: 21 keywords → 25,920 variants）

**预期收益**：低使用率 keyword 改 `shader_feature` 可大幅减少变体

**操作**：识别低使用率 keyword，逐个改为 `shader_feature`

### P4: Stripping 规则扩展

**判定条件**：
- 存在 editor/debug 专用 keyword（如 `_DEBUG`, `SHADER_API_EDITOR`, `_EDITOR_HLOD_BAKER`）
- 这些 keyword 不应出现在 player build 中

**预期收益**：通过 ShaderStripping 脚本在构建时移除

**操作**：在 `IPreprocessShaders.OnProcessShader()` 中添加 stripping 规则

### P5: 材质 Keyword 死代码

**判定条件**：
- 孤儿 keyword：材质启用了 keyword 但 shader 中不存在对应声明
- 无效启用：材质设置了 keyword 但运行时无效果

**预期收益**：清理材质 keyword 设置，减少编辑器噪音

**操作**：批量清理材质中的无效 keyword 设置

## 技术参考

### JNFS 包格式

JNFS 是 JN 引擎自定义的资源归档格式，由 `.idx`（索引）+ `.data`（数据）文件对组成。

**IDX 文件结构**：
```
Header:
  fileEntryCount (U32 BE)
  dataEntryCount (U32 BE)
DataEntry[] (28 bytes each):
  contentHash  (16 bytes, MD5)
  offset       (U32 BE, 在 .data 中的偏移)
  encodedSize  (U32 BE, 压缩后大小)
  decodedSize  (U32 BE, 解压后大小)
FileEntry[] (24 bytes each):
  pathHash     (U64 BE, 文件路径的 hash)
  contentHash  (16 bytes, 关联到 DataEntry)
```

**JNTE 压缩容器**：
```
Header:
  signature   (U32 BE = 0x4A4E5445 'JNTE')
  chunkCount  (U32 BE)
ChunkInfo[] (9 bytes each):
  type            (U8: 0=Raw, 1=LZ4, 2=LZMA, 3=Zstd)
  decompressedSize (U32 BE)
  compressedSize   (U32 BE)
ChunkData[]:
  compressed data bytes
```

**XOR 混淆还原**（仅 Zstd）：
- JN 引擎替换了 zstd magic: `0xFD2FB528` → `0xFA4BF25C`
- Frame header 中的 FCS 和 dictID 字段经 XOR 处理
- XOR 常量：U16=`0x4A4E`, U32=`0x4A4E5445`, U64=`0x637c777bf26b6fc5`

### Unity Shader 二进制结构

SerializedShader 字段按 Transfer() 顺序排列：

```
NamedObject.m_Name (String)          — 外层名称（player build 中常为空）
m_ParsedForm:
  m_PropInfo (SerializedProperties)  — shader 属性定义
  m_SubShaders[] (SerializedSubShader[])
    m_Passes[] (SerializedPass[])
      m_Programs[6] (Vertex/Fragment/Geometry/Hull/Domain/RayTracing)
        m_SubPrograms[] (old format)
        m_PlayerSubPrograms[][] (new format, 每个=一个变体)
  m_KeywordNames[] (String[])        — keyword 名称列表
  m_KeywordFlags[] (UInt8[], 可选)   — keyword flag (0=multi_compile, 1=shader_feature 等)
  m_Name (String)                    — 真正的 shader 名称
```

每个 `SerializedPlayerSubProgram` 包含：
- `m_BlobIndex`: 编译后字节码索引
- `m_KeywordIndices[]`: 此变体启用的 keyword 索引列表
- `m_ShaderRequirements`: GPU 特性要求
- `m_GpuProgramType`: 目标 GPU API

### .mat YAML Keyword 提取

Unity 材质文件是 YAML 格式，keyword 有两种写法：

```yaml
# 新格式
m_ValidKeywords:
  - _NORMALMAP
  - _EMISSION
  - _ALPHATEST_ON

# 旧格式
m_ShaderKeywords: _NORMALMAP _EMISSION _ALPHATEST_ON
```

### Keyword Ratio 计算逻辑

对每个 (shader, pass, stage) 组合中的每个 keyword：

```
ratio = 该 keyword ON 的变体数 / 该 stage 总变体数
```

- `ratio ≈ 0.5`：keyword 未被 strip，每个变体都有 on/off 两版 → P0 优化目标
- `ratio ≈ 0`：keyword 已被 strip 或从不启用 → P1 清理目标
- `ratio ≈ 1`：keyword 总是启用 → 可考虑硬编码

## CLI 用法

```bash
# 基本用法：解析包体并默认导出 Excel
python scripts/shader_variant_analyzer.py <game_data_dir> [-o output_dir]

# 含材质扫描：同时分析 .mat keyword 使用
python scripts/shader_variant_analyzer.py <game_data_dir> \
    --project-dir <unity_project_dir> \
    [-o output_dir]

# 只生成 Markdown/JSON，不导出 Excel
python scripts/shader_variant_analyzer.py <game_data_dir> --no-xlsx [-o output_dir]

# 完整示例
python skills/shader-variant-analyzer/scripts/shader_variant_analyzer.py \
    "C:/Users/Admin/Downloads/T3_development/Game_Data" \
    --project-dir "Project-T3-zhengyang.solis-development/client" \
    -o ShaderReport
```

**参数说明**：

| 参数 | 必选 | 说明 |
|------|------|------|
| `game_data_dir` | 是 | Game_Data 目录路径（含 .idx/.data 和/或 data.unity3d） |
| `-o, --output` | 否 | 报告输出目录，默认 `ShaderReport` |
| `--project-dir` | 否 | Unity 项目目录（含 Assets/），用于材质 keyword 扫描 |
| `--xlsx` | 否 | 导出 Excel，默认已开启；保留用于兼容旧命令 |
| `--no-xlsx` | 否 | 跳过 Excel 导出 |

## 输出文件结构

```
{output_dir}/
  summary.md                      — Shader 总览 + Top 20
  keyword_analysis.md             — 全局 keyword 频率 + ratio 分析
  shader_details.md               — 每个 shader 的详细 keyword 列表
  raw_data.json                   — 结构化原始数据
  optimization_recommendations.md — P0-P5 分级优化建议
  material_keyword_usage.md       — 材质 keyword 使用统计
  shader_pass_details.md          — Shader/Pass/Stage 细节
  shader_variant_report.xlsx      — 默认导入飞书表格的 Excel 报告
```

## Dependencies

- Python 3.7+
- `zstandard` — JNTE zstd 解压（`pip install zstandard`）
- `lz4` — JNTE/UnityFS LZ4 解压（`pip install lz4`）
- `openpyxl` — 默认 Excel 导出（`pip install openpyxl`）
- `lark-cli` — 默认导入飞书在线表格；使用前按 `lark-shared` 完成 user 身份认证和所需 scope

## Reference Scripts

- `scripts/shader_variant_analyzer.py` — 完整的端到端工具（解析 + 扫描 + 报告）
- 参见 `references/optimization-levels.md` — P0-P5 详细分级规则
- 参见 `references/binary-format.md` — JNFS + Unity 二进制格式技术参考

## 与默认 workflow / agents 的配合

此 skill 负责 shader 变体和 keyword 领域分析，并与 `workflow-doc-driven` 配合：

- 如果任务涉及教学、优化方案沉淀或多轮排查，先产出/更新 `guides/<topic>.md`
- 运行变体解析器、材质扫描、批量报告生成等命令密集步骤，优先使用 `task`
- 需要继续追到 shader 源码、材质资产、stripping 逻辑、构建管线时，优先使用 `codebase-explorer`
- 如果发现新的 keyword 污染模式、stripping 规则、或优化优先级调整，使用 `doc-updater`
- 如果修改了 shader、stripping 脚本或分析工具并需要中文解释改动，使用 `diff-explainer`
- 对可能影响渲染结果、构建产物或 shader 编译的改动，建议最终使用 `code-review`
