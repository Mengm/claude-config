---
name: unity-memory-profiler
description: Parse and analyze Unity Memory Profiler .snap binary files without the Unity Editor. Use when the user provides .snap files and wants memory reports, leak detection, VRAM analysis, comparative timelines, or code-level root cause investigation. Covers single-file analysis, batch processing, cross-snapshot diff, and source code diagnostic.
---

# Unity Memory Profiler .snap Analysis

Parse Unity Memory Profiler snapshot files (.snap) directly in Python, generate structured reports, detect memory leaks, and trace root causes in engine/game source code.

## When to use this skill

- User provides `.snap` files from Unity Memory Profiler
- User asks about memory leaks, VRAM growth, native object tracking in Unity
- User wants comparative analysis across multiple snapshots
- User needs code-level root cause investigation for memory issues

## Workflow

### Phase 1: Single Snapshot Parsing

Use `scripts/snap_parser.py` as the foundation parser (or regenerate from the reference spec below). The parser:

1. Opens the `.snap` binary file
2. Reads the TAIL section to locate the DIRECTORY
3. Reads the DIRECTORY to get chapter entries (one per ENTRY_TYPE)
4. For each chapter, reads blocks of data based on chapter format

Key data to extract per snapshot:
- **Metadata**: version, record date, user metadata, capture flags
- **Native Objects**: name, type, size, instance_id, flags, address
- **Native Types**: type names and base type hierarchy
- **GFX Resources**: NativeGfxResourceReferences (GPU VRAM, separate from native object sizes)
- **Scene Objects**: loaded scenes, build index, associated root IDs
- **Memory Labels**: allocator names and sizes (Texture, Mesh, Audio, etc.)
- **Managed Heap**: managed memory sections and stack data
- **Duplicates**: objects with identical name+type appearing multiple times

### Phase 2: Batch Individual Reports

For each `.snap` file, generate an individual markdown report containing:
- Snapshot metadata and timestamp
- Total native memory and GFX resource memory
- Top 50 objects by size
- Memory breakdown by native type
- Category breakdowns: Texture2D, RenderTexture, Mesh, AnimationClip, Cubemap, Shader, Font
- Scene list
- Duplicate objects (same name+type, multiple instances)
- Memory label summary

### Phase 3: Comparative Analysis

Compare all snapshots chronologically:
- Overview table: timestamp, native total, GFX total, object count, scene
- Memory trend analysis (growth rate, peak, cumulative delta)
- Persistent heavy hitters (objects present in all snapshots)
- Growing resource categories (which types increase over time)
- Scene transition correlation (memory jumps at scene changes)
- VRAM root cause analysis
- Optimization priority recommendations

### Phase 4: Detailed Leak Timeline

For each consecutive snapshot pair, compute:
- **Diff**: new objects, removed objects, size changes
- **Category deltas**: per-type memory change (Texture2D, Mesh, etc.)
- **Scene transition leaks**: resources from old scene surviving in new snapshot
- **Origin guessing**: map resource names to scene/system categories using heuristics
- **Cumulative leak summary**: resources in final snapshot not present in initial

### Phase 5: Code Diagnostic (optional)

When engine/game source code is available, investigate root causes:
- Search for `DontDestroyOnLoad` usage patterns
- Check scene transition cleanup (`Resources.UnloadUnusedAssets()`, `GC.Collect()`)
- Inspect resource loading/unloading systems (ashcan queues, delayed unload)
- Review streaming managers and their dispose patterns
- Look for static references holding resources (static dictionaries, static RenderTextures)
- Generate a prioritized issue list (P0/P1/P2) with code locations and fix proposals

## .snap Binary Format Specification

### File Structure
```
[HEAD_SIGNATURE: 0xAEABCDCD (4 bytes, little-endian uint32)]
[Block data...]
[DIRECTORY_SIGNATURE: 0xCDCDAEAB]
[Chapter Section Version: 0x20170724]
[Block Section Version: 0x20170724]
[Chapter count (uint32)]
[Chapter entries...]
[Block count (uint32)]
[Block entries...]
[TAIL_SIGNATURE: 0xABCDCDAE]
[Directory offset (uint64)]
```

### Reading order
1. Seek to end-of-file minus 12 bytes
2. Read TAIL_SIGNATURE (uint32) and directory_offset (uint64)
3. Seek to directory_offset, read DIRECTORY_SIGNATURE
4. Read chapter_section_version, block_section_version
5. Read chapter_count, then chapter entries
6. Read block_count, then block entries
7. For each chapter, use its block indices to read actual data

### Block format
```
[chunk_size (uint64)]
[data (chunk_size bytes)]
```

### Chapter formats

**SingleValue** (format=1):
- header_block_index, data_block_index
- Data block contains raw bytes (interpret based on entry type)

**ConstantSizeArray** (format=2):
- header_block_index, data_block_index
- Header: entry_count (uint32), entry_size (uint32)
- Data: entry_count * entry_size bytes of packed values

**DynamicSizeArray** (format=3):
- header_block_index, data_block_index, sizes_block_index
- Header: entry_count (uint32)
- Sizes: entry_count * uint32 (byte length of each entry)
- Data: concatenated variable-length entries (typically UTF-8 strings)

### 76 Entry Types (index order matters)

See `references/entry_types.md` for the complete list. Key entries:

| Index | Name | Format | Description |
|-------|------|--------|-------------|
| 0 | Metadata_Version | SingleValue | Snapshot format version |
| 1 | Metadata_RecordDate | SingleValue | Capture timestamp |
| 5 | NativeTypes_Name | DynamicSizeArray | Type name strings |
| 7 | NativeObjects_NativeTypeArrayIndex | ConstantSizeArray | Type index per object |
| 10 | NativeObjects_InstanceId | ConstantSizeArray | Instance ID per object |
| 11 | NativeObjects_Name | DynamicSizeArray | Object name strings |
| 13 | NativeObjects_Size | ConstantSizeArray | Object size in bytes |
| 60 | SceneObjects_Name | DynamicSizeArray | Scene names |
| 67 | NativeGfxResourceReferences_Id | ConstantSizeArray | GFX resource IDs |
| 68 | NativeGfxResourceReferences_Size | ConstantSizeArray | GFX resource sizes (VRAM) |

## Key Analysis Patterns

### Type aggregation
Group objects by NativeType, sum sizes. Top types are typically: Texture2D, Mesh, Shader, Material, AnimationClip, RenderTexture, Font, Cubemap.

### Duplicate detection
Group objects by (name, type). Any group with count > 1 is a potential leak (same asset loaded multiple times).

### Diff analysis between snapshots
```python
prev_keys = {(obj['name'], obj['type']): obj for obj in prev_objects}
curr_keys = {(obj['name'], obj['type']): obj for obj in curr_objects}
new_objects = [curr_keys[k] for k in curr_keys if k not in prev_keys]
removed_objects = [prev_keys[k] for k in prev_keys if k not in curr_keys]
```

### Origin guessing heuristic
Map resource names to likely scene/system by keyword matching:
- `ui_`, `UI/`, `Atlas` -> UI system
- `fx_`, `VFX/`, `particle` -> VFX
- `env_`, `terrain`, `building` -> Environment
- `char_`, `hero_`, `monster_` -> Character
- `bgm_`, `sfx_`, `sound` -> Audio

### Scene transition leak detection
When scene changes between snapshots, check if objects associated with the OLD scene name still exist in the new snapshot. These are leaked resources.

## Common Unity Memory Issues to Check

1. **No `Resources.UnloadUnusedAssets()` after scene transitions** (P0)
2. **`DontDestroyOnLoad` overuse** - objects surviving scene changes unnecessarily (P0)
3. **Delayed unload queues with insufficient capacity or too-long wait times** (P1)
4. **Scene switch without cleanup window** - loading new scene before old one fully unloads (P1)
5. **Streaming manager not properly disposing on scene change** (P1)
6. **Static references to RenderTextures, Meshes, Materials** (P2)
7. **AssetPool/ObjectPool marked DontDestroyOnLoad holding scene-specific assets** (P2)

## Output File Naming Convention

```
{output_dir}/
  01_Individual/
    {snap_filename_without_ext}.md
  02_Comparative_Analysis.md
  03_Detailed_Leak_Timeline.md
  04_Code_Diagnostic_Report.md   (if source code available)
  summary.json
```

## Dependencies

- Python 3.7+ (stdlib only: `struct`, `os`, `sys`, `json`, `collections.defaultdict`)
- No external packages required
- No Unity Editor dependency

## Reference Scripts

The following scripts in the project root serve as working implementations:
- `analyze_snap.py` — Foundation parser with SnapReader class, console output for single file
- `batch_analyze_snap.py` — Batch processing, individual MD reports, comparative MD
- `detailed_leak_timeline.py` — Cross-snapshot diff analysis, leak timeline
- `analyze_0306.py` — Combined all-in-one script (demonstrates full pipeline)

## 与默认 workflow / agents 的配合

此 skill 是 Unity `.snap` 分析的领域流程，默认与 `workflow-doc-driven` 叠加使用：

- 如果任务需要教学、跨快照方法复用或后续追踪，先产出/更新 `guides/<topic>.md`
- 解析 `.snap`、批量生成报告、跑 comparative/timeline 脚本等命令密集步骤，优先使用 `task`
- 当需要把内存现象继续追到项目源码中的场景切换、资源管理、静态引用或 unload 逻辑时，优先使用 `codebase-explorer`
- 如果调试过程中确认了新的根因、修复方向或分析启发式，使用 `doc-updater` 同步文档
- 如果随后修改了资源释放代码、分析脚本或排障辅助工具，需要中文变更说明时，使用 `diff-explainer`
- 对涉及生命周期和资源管理的实质代码修复，建议收尾时使用 `code-review`
