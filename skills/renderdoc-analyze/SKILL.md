---
description: 基于 RenderDoc MCP 分析 .rdc 截帧文件，结合本地代码推断渲染问题的可能原因。当用户提供 .rdc 截帧 + 问题描述（闪烁、黑屏、颜色异常、性能差、特定物体渲染错误等），需要定位问题时触发。
---

# RenderDoc 截帧分析 — 问题推断工作流

## 触发时机

当用户同时提供以下两个输入时：

1. **一个 .rdc 截帧文件**（RenderDoc 捕获）
2. **问题描述**（自然语言，如"这一帧人物身上闪白"、"角色头发颜色不对"、"这一帧掉到 30fps"、"后处理光晕异常"）

目标：结合截帧的 GPU 状态 + 本地渲染代码（Shader / 材质 / Pipeline 配置），给出**有根据的问题推断方向**，而不是盲猜。

## 工作流程

### 第零步：需求拆解

收到用户输入后，先做结构化拆解：

1. **确认 .rdc 绝对路径**。如果用户给的是相对路径或模糊名字，先 Glob 定位。
2. **抽取问题关键词**，映射到可能的渲染阶段：
   - 颜色/亮度异常 → Pixel Shader / 后处理 / Color Grading / Tone Mapping
   - 闪烁/抖动 → TAA / 帧间插值 / Jitter / Uninitialized Memory
   - 几何错误（穿模/丢面） → Vertex Shader / 剔除 / 深度 / Culling
   - 透明度/排序错误 → Blend State / 渲染顺序 / Depth Write
   - 性能问题 → Draw Call 数量 / Overdraw / 带宽 / 状态切换
   - 阴影异常 → Shadow Map / Light / Cascade
   - UI 异常 → UI 渲染 Pass / Scissor / Viewport
3. **列出初步假设**（2~4 个候选方向），向用户简要确认聚焦范围，再开始深度分析。

### 第一步：打开截帧并建立全局画像

**必须按顺序执行**：

1. `open_capture(path=<.rdc 绝对路径>)` — 打开截帧
2. `get_capture_info()` — 查看：
   - **GPU/驱动**：识别是否是 Adreno / Mali / PowerVR / Apple GPU
   - **API**：D3D11 / D3D12 / Vulkan / GLES
   - **known_gpu_quirks**：工具已检测到的平台风险点（关键信号！）
3. `get_frame_overview()` — 获取 Draw Call 总数、Clear 次数、RT 列表，建立"这一帧长什么样"的整体认知

这一步的产出是一份**截帧画像**：API、GPU、Draw 数量、主要 Render Target 列表、潜在 GPU quirks。把它记在心里并在最终报告中引用。

### 第二步：根据问题方向定位嫌疑 Draw Call

针对不同类型的问题，用对应的工具集：

#### A. 颜色 / 亮度 / 后处理类问题

1. `list_actions(filter="<关键词>")` — 按名称搜索（如 `filter="PostProcess"`, `filter="Tonemap"`, `filter="Bloom"`）
2. 对嫌疑 pass 的最后几个 draw call：
   - `set_event(event_id=<id>)` → `get_draw_call_state()` 一次性取 pipeline 概览
   - `sample_pixel_region(x, y, width, height)` — 扫描问题区域找 NaN / Inf / 负值
3. 如果像素值异常：
   - `pixel_history(x, y)` — 追溯该像素被哪些 draw call 写入过
   - `debug_shader_at_pixel(x, y)` — 对异常像素做 shader step-by-step 调试

#### B. 闪烁 / 帧间抖动类问题

1. `diagnose_negative_values()` — 检测 R11G11B10 等无符号格式里的负值（Mali/Adreno 常见问题）
2. `find_draws(filter="TAA" 或 "Temporal")` — 定位 TAA 相关 draw
3. `get_shader_reflection` + `get_cbuffer_contents(filter="jitter|blend|history")` — 检查时域混合系数

#### C. 几何 / 穿模 / 剔除问题

1. `find_draws(filter="<物体名>")` — 定位相关 draw
2. `get_vertex_inputs()` — 确认 vertex buffer / IB 绑定
3. `get_pipeline_state()` — 关注：
   - Rasterizer：cull mode、fill mode、front face winding
   - Depth/Stencil：depth test / write / compare func
4. `get_post_vs_data(event_id)` — 查看 VS 输出，确认顶点变换是否正确

#### D. 透明度 / 排序问题

1. 定位半透明 pass 的 draw 列表
2. `get_pipeline_state()` 检查每个 draw 的 Blend State 和 Depth Write
3. `analyze_render_passes()` — 查看 pass 划分和 RT 切换时机

#### E. 性能问题

1. `get_pass_timing(granularity="pass")` — 找最贵的 Pass
2. `analyze_overdraw()` — 填充率压力
3. `analyze_bandwidth()` — 带宽瓶颈
4. `analyze_state_changes()` — 状态切换 / 批次合并机会
5. `diagnose_mobile_risks(check_categories=["performance","precision","compatibility"])` — 移动端专项风险清单

#### F. 阴影 / 光照问题

1. `find_draws(filter="Shadow" / "Depth")` — 定位 shadow map 生成 pass
2. `list_textures(filter="shadow")` — 列出相关 RT
3. `save_texture` — 必要时把 shadow map 导出成 PNG 肉眼确认

### 第三步：结合本地代码交叉验证

这是本 skill 与纯 RenderDoc 分析的核心差异：**不仅要看 GPU 状态，还要对照本地代码确认是谁生成了这些 draw**。

定位到嫌疑 shader / pass 后：

1. **从 shader 名或 RT 名反查代码**：
   - `get_shader_reflection()` 拿到 shader entry point 或 debug name
   - 用 Grep 搜索 shader 源码（通常在 `code/`、`client/` 或 `assets/Shaders/` 下）
   - 用 Grep 搜索 C# / Lua 侧的材质/RT 设置代码
2. **对齐 CBuffer 数据和代码默认值**：
   - `get_cbuffer_contents(filter="<变量名>")` 取实际运行时值
   - 在代码里搜索同名变量，确认"期望值 vs 实际值"是否一致（经典 bug：某个 scalar 忘了传、或者传了默认值 0）
3. **对齐 Pipeline 状态和材质配置**：
   - 例如 Blend 模式异常 → 去找对应 Material / ShaderLab 的 Blend 语句
   - Cull 模式异常 → 检查材质 RenderState 配置
4. **对齐 Draw Order 和代码调度**：
   - 如果渲染顺序不对，找到 pass 注册/排序的代码（常见位置：SRP、CommandBuffer 构造、RenderPipeline）

### 第四步：输出推断报告

按以下固定结构输出，便于用户快速判断：

```markdown
## RenderDoc 分析报告

### 1. 截帧画像
- API / GPU / 驱动
- Draw 数量 / 主要 RT 列表
- 检测到的 GPU quirks（如有）

### 2. 问题聚焦
- 用户问题：<原始描述>
- 聚焦方向：<第零步确认的方向>

### 3. 关键证据
| 证据来源 | EID | 工具/方法 | 发现 |
|---------|-----|----------|------|
| draw call | 1234 | get_draw_call_state | ... |
| pixel history | (512,256) | pixel_history | ... |
| cbuffer | 1234 | get_cbuffer_contents | `_Exposure = 0.0`（异常） |
| 代码交叉 | - | Grep `ShaderFile.hlsl:42` | ... |

### 4. 问题推断（按可能性排序）
1. **最可能原因**：<一句话结论>
   - 支持证据：引用上表的行
   - 对应代码位置：[file.lua:line](path#Lline)
   - 验证方法：<用户可以做的下一步>
2. **次可能原因**：...
3. **其他需排查**：...

### 5. 未覆盖 / 不确定的地方
- 明确说明哪些点还没查
- 需要用户补充什么信息
```

### 第五步：清理

分析完成后，调用 `close_capture()` 释放资源。MCP server 进程退出时也会自动清理，但显式关闭是好习惯。

## 关键注意事项

1. **先看 GPU quirks**：`get_capture_info()` 返回的 `known_gpu_quirks` 是白送的线索，很多移动端 bug 直接就在这一步定位出来
2. **不要盲目 dump 所有 draw**：42 个工具不是都要用一遍，按问题类型选最相关的 3~5 个
3. **像素级问题用像素级工具**：颜色异常直接 `sample_pixel_region` + `pixel_history`，比逐个 draw 翻快得多
4. **CBuffer 对照代码**：很多"神秘 bug" 都是 CBuffer 某个字段没传 / 传错类型 / 跨 frame 脏数据。拿到实际值后**一定要**和代码对照
5. **不要直接下结论**：RenderDoc 告诉你"发生了什么"，本地代码告诉你"为什么"。两边对不上的地方才是根因
6. **区分渲染问题和引擎问题**：如果 draw call 数量异常，问题可能在 C#/Lua 调度层，不在 shader
7. **离线格式警告**：如果 `open_capture` 失败，优先检查 .rdc 是否是匹配版本（本项目的 binary 是 v1.43 自编译）
8. **移动端截帧**：如果 API 是 GLES / Vulkan 且 GPU 是 Adreno/Mali，务必跑一次 `diagnose_mobile_risks`

## 常见失误

- ❌ 只看 `list_actions` 的名字就下结论，不看 pipeline state
- ❌ 看到 CBuffer 里的值"看起来正常"就跳过，没和代码期望值对照
- ❌ 性能问题只看 `get_pass_timing`，不看 overdraw / bandwidth / state changes
- ❌ 分析完不 `close_capture`，多个截帧叠加导致状态污染
- ❌ 不先 `set_event` 就调用依赖当前事件的工具（如 `get_pipeline_state`）

## 报告语气

- **推断**而非**断言**：用"最可能是..."、"证据指向..."、"需要进一步验证..."
- 所有结论必须有**证据引用**（EID + 工具名 + 关键数值）
- 代码引用必须用 Markdown 链接格式：`[file.lua:42](path/file.lua#L42)`
- 不确定的地方必须明确标注，不要用"应该"、"可能"混淆已验证和未验证的事实
