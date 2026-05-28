---
name: analysis-profiler-data
description: Unity Profiler .data 文件性能分析。解析二进制采样数据，生成性能报告和卡顿帧分析，以专家视角给出优化建议并写入飞书文档。触发场景 (1) 分析 Profiler .data 文件 (2) 卡顿/掉帧分析 (3) Unity 性能优化建议 (4) 用户提供 .data 文件路径。即使没有明确说 profiler，只要涉及 Unity 性能数据文件分析都应触发。
---

# Unity Profiler .data 性能分析

将 Unity Profiler 二进制 `.data` 文件转化为可操作的性能洞察。

## 工具位置

分析脚本位于本 skill 目录中：

```
~/.claude/skills/analysis-profiler-data/scripts/
├── unity_profiler_parser.py   # 主解析器 + 总体分析报告
└── stutter_analysis.py        # 卡顿帧专项分析
```

使用时通过 `~/.claude/skills/analysis-profiler-data/scripts/` 的绝对路径调用，不依赖任何项目。

## 分析流程

### Step 1: 总体性能分析

运行主解析器生成全面报告：

```bash
python ~/.claude/skills/analysis-profiler-data/scripts/unity_profiler_parser.py "<path_to.data>"
```

输出自动保存到 `<path_to.data>.analysis.txt`。

报告包含：
- **帧时间概览**：平均/中位/P90/P95/P99、直方图、变异系数
- **CPU 时间分类**：Scripts、Rendering、Animation、Physics、UI、Audio 等各类别耗时占比
- **渲染统计**：DrawCalls、Batches、三角面数、Shadow Casters、SetPass Calls
- **内存统计**：总内存、GC 分配、纹理/Mesh/音频内存
- **线程信息**：各线程采样数和 GC 分配量
- **Top 30 热点 Marker**：按总耗时排序，含平均/最大值和调用次数
- **GC 分配热点**：引起 GC 分配最多的 Marker
- **Main Thread 调用树**：展示典型帧的函数调用层级
- **优化建议**：基于已知 Marker 模式自动生成

可选 JSON 导出：
```bash
python ~/.claude/skills/analysis-profiler-data/scripts/unity_profiler_parser.py "<path_to.data>" --json output.json
```

### Step 2: 卡顿帧分析

运行卡顿帧分析器深入排查掉帧问题：

```bash
python ~/.claude/skills/analysis-profiler-data/scripts/stutter_analysis.py "<path_to.data>"
```

输出自动保存到 `<path_to.data>.stutter_analysis.txt`。

报告包含：
- **帧时间分布**：统计指标 + ASCII 直方图
- **卡顿检测**：轻微卡顿（>1.5x 中位数）和严重卡顿（>3x 中位数）
- **连续卡顿检测**：连续多帧超阈值的片段
- **卡顿帧详细分析**：每个卡顿帧的 Spike 贡献者（对比该 Marker 的全局平均值）
- **调用树**：卡顿帧的 Main Thread 调用层级
- **卡顿模式分析**：GPU 等待、脚本、渲染、GC 等分类
- **周期性检测**：是否存在周期性卡顿
- **帧时间趋势**：ASCII 趋势图

### Step 3: 专家级解读

读取两份报告后，以 Unity 性能优化专家视角进行深度分析。关注以下维度：

**帧率与稳定性**
- 目标帧率（30fps=33.3ms, 60fps=16.6ms）是否达标
- 帧时间变异系数（CV < 0.2 为稳定，> 0.5 为严重不稳定）
- 卡顿占比是否可接受（< 1% 为优秀）

**CPU 瓶颈定位**
- Scripts（Lua/C#）占比是否过高（> 30% 需关注）
- Rendering Pipeline 耗时（SRP Batcher 效率、Shadow 开销）
- Animation/Physics 是否合理
- UI 系统开销（Canvas rebuild、Raycaster 数量）
- GC 分配频率和大小

**GPU 瓶颈信号**
- `Gfx.WaitForPresentOnGfxThread` 占比大 → GPU 瓶颈
- Batch/DrawCall 数量（移动端建议 < 500）
- Shadow Caster 数量（建议 < 200）
- 三角面数是否合理

**内存风险**
- 总内存接近设备上限（如 8GB 设备 > 6GB 需警惕）
- GC 每帧分配量（> 1KB/frame 需优化）
- 纹理内存占比

**脚本性能**（如有 xLua/ILRuntime）
- Lua 桥接调用开销
- C#→Lua 调用频率

**优化建议优先级**
按影响力排序给出具体可操作的优化建议，每条包含：
1. 问题描述和量化数据
2. 根因分析
3. 具体优化方案

### Step 4: 写入飞书文档

分析完成后，**必须**使用 feishu-doc skill 创建飞书文档并写入完整分析报告。文档标题格式：`"<数据文件名> Profiler 性能分析报告"`。

报告结构建议：
1. 总体概览（设备/场景/帧数/目标帧率）
2. 帧时间分析（统计指标 + 分布）
3. CPU 瓶颈分析（各类别占比 + 热点 Marker）
4. 渲染管线分析（Batch/DrawCall/Shadow/SRP Batcher）
5. 内存分析（总内存/GC/纹理）
6. 卡顿帧分析（检测结果 + 逐帧详情）
7. 优化建议（按优先级排序，含量化数据和具体方案）

写入完成后，将文档链接发给用户。

## 关键 API 注意事项

使用 `unity_profiler_parser.py` 作为库时：

```python
from unity_profiler_parser import UnityProfilerParser

parser = UnityProfilerParser("path/to/file.data")
parser.parse()                    # 注意：不返回值，数据存储在 parser 内部
frames = parser.frames            # List[FrameData]
markers = parser.markers          # Dict[str, marker_info]
report = parser.analyze()         # 返回文本报告字符串
```

**FrameData** 结构：
- `frame_index`, `real_frame`: 帧索引
- `total_cpu_us`, `total_gpu_us`: CPU/GPU 微秒
- `stats`: 包含 `batches`, `triangles`, `mem_total_bytes`, `mem_gc_alloc_bytes` 等
- `threads`: `List[ThreadInfo]`

**ThreadInfo** 结构：
- `thread_name`, `group_name`: 线程标识
- `samples`: `List[SampleInfo]`（按调用树前序遍历排列）
- `total_gc_alloc`: GC 分配总量

**SampleInfo** 结构：
- `marker_name`: Marker 名称（不是 `marker_id`）
- `duration_ns`: 持续时间纳秒（不是 `time_ns`）
- `start_time_ns`: 起始时间
- `child_count`: 子采样数量
- `gc_alloc`: GC 分配字节数

## 支持的格式

- Unity 2022.3 Profiler 二进制 `.data` 文件（Editor 保存格式）
- 协议版本：0x20170327 ~ 0x20220328
- 这不是 `.raw` 格式（那是 ProfilerRecorder 输出），需要通过 Unity Editor 的 Profiler 窗口 Save 导出
