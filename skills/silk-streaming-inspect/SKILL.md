---
name: silk-streaming-inspect
description: 解析 Silk Streaming 导出的二进制场景数据（layer_block_00_00.bin、block_XX_YY.bin），用于排查动态图层加载问题。当用户需要查询某场景有哪些动态图层、某动态图层导出了哪些 streaming asset、某 prefab 是否在某图层中、某 block 文件包含哪些资源、AssetType/LoadDistance/CustomLoadControlData 字段值时使用。触发词：动态图层、custom layer、layer_block、BlockV2、SetEnabledCustomLayerIds、Silk streaming、导出资产、CustomLayerId、HasCustomLayer、StreamingAssetHeader、动态图层加载不出来。
---

# Silk Streaming 导出数据查询

排查 Silk Streaming 动态图层（custom layer）加载问题时，常需要确认：
- 某场景配置了哪些动态图层、layerId 是多少
- 某图层导出后实际包含哪些 streaming asset
- 某 prefab 属于哪个图层、AssetType / LoadDistance / CustomLoadControlData 是什么
- 开启 VirtualGeometry 后某些 ECS 资源被过滤的根因

本 skill 通过 Python 脚本直接解析 `ReleaseData/Silk/BlockV2~/` 下的二进制数据。

## 脚本位置

`F:\Perforce\Project-T3-baiyuan\.claude\skills\silk-streaming-inspect\parser.py`

通过 Bash 调用：

```bash
python "F:/Perforce/Project-T3-baiyuan/.claude/skills/silk-streaming-inspect/parser.py" <subcommand> [args...]
```

## 子命令

### 1. `list-layers <scene>` — 列出场景所有动态图层

输出每个图层的 layerId、name、layer_block 中的空间索引节点数。

```bash
python parser.py list-layers TaijiBase_ConstructedArmor_Objective_01a
```

`<scene>` 可以是：
- 场景名（自动拼接到 `client/Assets/ResTemp/Scene/PCGLevel/Lithos/`）
- streaming.prefab 完整路径
- 包含 `ReleaseData/` 的目录路径

### 2. `query-layer <scene> <layer>` — 查询某图层的所有 streaming asset

`<layer>` 接受 layerId（整数，含负数）或 layer 名称。输出包括：
- 每个 asset 的 block 文件、位置、AssetType（ECS/HIMR/Collision/VirtualGeometry...）、SceneObjectLevel、LoadDistance、CustomLoadControlData（CLCD）
- 该图层关联的所有 prefab 名（按 block 分组）

```bash
python parser.py query-layer TaijiBase_ConstructedArmor_Objective_01a BossFight02
python parser.py query-layer TaijiBase_ConstructedArmor_Objective_01a -1603526523
```

**关键字段含义：**
- `AssetType`: `2=ECS`, `3=HIMR`, `4=Collision`, `5=VirtualGeometry`
- `CLCD=1` 表示该 asset 由 VirtualGeometry 替代，开启 VG 时会被 CalcDistanceJob 过滤掉

### 3. `query-block <block_file> [--scene <scene>]` — 查询某个 block 文件内容

- 对 `layer_block_*.bin`：列出空间索引节点（中心、尺寸、bitmask、数据偏移/长度）
- 对 `block_XX_YY.bin`：列出文件中检测到的 CustomLayerId 分布、所有 prefab 名

```bash
python parser.py query-block "f:/.../BlockV2~/block_07_08.bin"
python parser.py query-block block_07_08.bin --scene TaijiBase_ConstructedArmor_Objective_01a
```

### 4. `search-asset <scene> <prefab>` — 按 prefab 名搜索所在图层

输出该 prefab 名在哪些 block 中被引用（offset），并列出每个 block 中各图层的 asset header 数量、与 prefab 名引用位置的最小距离，供人工判断归属：

- **距离很近（< 5KB）** → 该 prefab 大概率属于该图层
- **距离很远（> 30KB）** → 该 prefab 大概率不属于该图层

```bash
python parser.py search-asset TaijiBase_ConstructedArmor_Objective_01a Building_Lithos_Print_Floor_07a
```

要严格确认归属，对比 `query-layer` 输出中的 prefab 名列表。

## 典型排查流程

**用户："某动态图层调用 SetEnabledCustomLayerIds 后没加载出来 prefab X"**

1. `list-layers <scene>` 确认场景有该动态图层、记下 layerId、确认 spatial nodes > 0（否则导出阶段就有问题）
2. `search-asset <scene> X` 确认 prefab 在 BlockV2 数据里、所属图层正确
3. `query-layer <scene> <layerName>` 检查 asset 字段：
   - 如果只有 `AssetType=Collision` 加载出来 → 看 ECS/HIMR 行的 `CLCD`
     - `CLCD=1` 且开启 VG → 等待 VirtualGeometry 类型 asset，但本图层可能没导出 VG → 导出问题或运行时关闭 VG
     - `CLCD=0` → 应正常加载，检查 LoadDistance 与玩家距离
   - 检查 `SceneObjectLevel` 是否在 `s_EnabledSceneObjectLevel` 中（默认 Level1/2/3 都启用）
4. 仍排查不出 → `query-block layer_block_00_00.bin --scene <scene>` 看 bitmask 是否覆盖该图层（bit 索引对应 `AvailableCustomLayerIds` 的 index）

## 数据结构参考

**StreamingAssetHeader**（ZeroFormatter，定义于 `PackageRepo/com.jngame.silk-streaming/Runtime/V2/StreamingHeader.cs:110`）

字段顺序紧密排列在 CustomLayerId 之后：

| 偏移（相对 CustomLayerId） | 字段 | 类型 | 说明 |
|---|---|---|---|
| -28 ~ -16 | Bounds.center | Vector3 | 世界坐标中心 |
| -12 ~ 0 | Bounds.extents | Vector3 | 包围盒尺寸 |
| 0 | CustomLayerId | int | 图层 ID（layer hash，与 _streaming.prefab 中的 AvailableCustomLayerIds 对应） |
| 4 | Offset | int | 头表内偏移 |
| 8 | AssetType | short | 资产类型 |
| 10 | SceneObjectLevel | short | 场景物体级别 |
| 12 | LoadDistance | float | 加载距离 |
| 16 | CustomLoadControlData | int | VG 控制位 |

**layer_block_00_00.bin entry（121 字节）**

| 偏移 | 字段 | 说明 |
|---|---|---|
| 0 | entry_index | entry 序号（0=header） |
| 8 | child_count or 0x7FFFFFFF | header 时为子节点数 |
| 40~48 | center xyz | 节点中心（float×3） |
| 56~64 | extents xyz | 节点尺寸（float×3） |
| 92 | data_offset | 关联数据偏移（指向其它 block 文件的偏移） |
| 96 | data_size | 关联数据长度 |
| 112 | bitmask | 图层归属位掩码（bit N = AvailableCustomLayerIds[N]） |

**运行时过滤（`StreamingAssetLoaderV2.cs:CalcDistanceJob`）**

```csharp
if (AssetType == ECS || AssetType == HIMR)
    bFilterVG = (!enableVG || CustomLoadControlData == 0);
else if (AssetType == VirtualGeometry)
    bFilterVG = enableVG;

return bFilterVG
    && enabledSceneObjectLevel.ContainsKey(SceneObjectLevel)
    && enabledCustomLayerIds.ContainsKey(CustomLayerId);
```

`SetEnabledCustomLayerIds` 自动添加 `0` 和 `-1`（NormalLayerId）到启用集合，所以无 custom layer 标记的资产始终通过过滤。

## 限制与注意

- 解析基于本仓库当前的 ZeroFormatter 二进制布局逆向得到，若 Silk 版本升级、字段顺序调整需重新校验。
- prefab 名提取使用正则 `(Building|Prop|FX|VFX|Env|Anim|Char|NPC)_*`，命名前缀不在此列的资产可能漏报。
- `search-asset` 的图层归属推断基于 ±5KB 邻近 CustomLayerId 字节的命中，存在误判可能；以 `query-layer` 的精确字段值为准。
- 非 Windows 平台需注意路径分隔符；脚本内部已统一使用 forward slash。
