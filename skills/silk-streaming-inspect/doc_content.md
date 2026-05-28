# 一、工具用途

排查 Silk Streaming **动态图层（custom layer）加载问题**时，常需要确认：

- 某场景配置了哪些动态图层、layerId 是多少
- 某图层导出后实际包含哪些 streaming asset
- 某 prefab 属于哪个图层、AssetType / LoadDistance / CustomLoadControlData 是什么
- 开启 VirtualGeometry 后某些 ECS 资源被过滤的根因

本工具通过 Python 脚本直接解析 `ReleaseData/Silk/BlockV2~/` 下的二进制数据，无需启动 Unity。

# 二、脚本位置

脚本路径：

```
F:\Perforce\Project-T3-baiyuan\.claude\skills\silk-streaming-inspect\parser.py
```

调用方式：

```bash
python "F:/Perforce/Project-T3-baiyuan/.claude/skills/silk-streaming-inspect/parser.py" <subcommand> [args...]
```

也可让 Claude Code 自动触发：在对话中说"动态图层加载不出来"、"BossFight02 这个 layer 有哪些资源"、"layer_block 里有什么"等关键词，Claude 会自动调用本 skill。

# 三、四个子命令详解

## 3.1 list-layers — 列出场景所有动态图层

输出每个图层的 **layerId、name、layer_block 中的空间索引节点数**。

```bash
python parser.py list-layers TaijiBase_ConstructedArmor_Objective_01a
```

`<scene>` 参数支持三种形式：

- 场景名（自动拼接到 `client/Assets/ResTemp/Scene/PCGLevel/Lithos/`）
- streaming.prefab 完整路径
- 包含 `ReleaseData/` 的目录路径

**示例输出：**

```
场景: TaijiBase_ConstructedArmor_Objective_01a
streaming prefab: client\Assets\ResTemp\Scene\PCGLevel\Lithos\...
动态图层共 12 个：

idx        layerId  layer name                 spatial nodes
----------------------------------------------------------------
  0    -1603526523  BossFight02                           76
  1     -197455886  door_4_open                           72
  2     -461395162  BossFight                             78
  ...
```

**关键判断：** `spatial nodes = 0` 表示 layer_block 中没有此图层的空间索引节点，导出阶段就有问题。

## 3.2 query-layer — 查询某图层的所有 streaming asset

`<layer>` 接受 **layerId（整数，含负数）或 layer 名称**。

```bash
python parser.py query-layer TaijiBase_ConstructedArmor_Objective_01a BossFight02
python parser.py query-layer TaijiBase_ConstructedArmor_Objective_01a -1603526523
```

**输出字段：**

- 每个 asset 的 **block 文件**、位置、AssetType（ECS / HIMR / Collision / VirtualGeometry）
- SceneObjectLevel（0=Level1, 1=Level2, 2=Level3）
- LoadDistance
- CustomLoadControlData（CLCD）
- 该图层关联的所有 prefab 名（按 block 分组）

**示例输出：**

```
图层: BossFight02 (layerId=-1603526523, index=0)

共找到 4 个 streaming asset：

block                  pos                      ext                    AssetType       SOL      LoadDist  CLCD
--------------------------------------------------------------------------------------------------------------
block_07_08.bin        (467.7,165.3,559.1)      (75.0,1.3,27.1)        2(ECS)          Level1      256.0     1
block_07_08.bin        (467.7,165.3,559.1)      (75.0,1.2,27.1)        3(HIMR)         Level1      130.0     0
block_07_09.bin        (467.7,165.3,586.1)      (75.0,1.3,27.1)        2(ECS)          Level1      256.0     1
block_07_09.bin        (467.7,165.3,586.1)      (75.0,1.2,27.1)        3(HIMR)         Level1      130.0     0
```

**重要字段说明：**

- **AssetType = 2 (ECS)**：通用渲染实体，开启 VirtualGeometry 时会按 CLCD 判断是否过滤
- **AssetType = 3 (HIMR)**：硬件实例化网格渲染器
- **AssetType = 4 (Collision)**：碰撞体（不受 VG 影响，始终加载）
- **AssetType = 5 (VirtualGeometry)**：VG 资源
- **CLCD = 1**：该 asset 由 VirtualGeometry 替代，**开启 VG 时会被 CalcDistanceJob 过滤掉**
- **CLCD = 0**：始终加载（不受 VG 影响）

## 3.3 query-block — 查询某个 block 文件内容

```bash
python parser.py query-block "f:/.../BlockV2~/block_07_08.bin"
python parser.py query-block block_07_08.bin --scene TaijiBase_ConstructedArmor_Objective_01a
```

- 对 `layer_block_*.bin`：列出空间索引节点（中心、尺寸、bitmask、数据偏移 / 长度）
- 对 `block_XX_YY.bin`：列出文件中检测到的 CustomLayerId 分布、所有 prefab 名

## 3.4 search-asset — 按 prefab 名搜索所在图层

输出该 prefab 名在哪些 block 中被引用（offset），并列出每个 block 中各图层的 asset header 数量、与 prefab 名引用位置的最小距离，供人工判断归属。

```bash
python parser.py search-asset TaijiBase_ConstructedArmor_Objective_01a Building_Lithos_Print_Floor_07a
```

**判断规则：**

- **距离很近（< 5KB）** → 该 prefab 大概率属于该图层
- **距离很远（> 30KB）** → 该 prefab 大概率不属于该图层

要严格确认归属，对比 `query-layer` 输出中的 prefab 名列表。

# 四、典型排查流程

**场景：某动态图层调用 `SetEnabledCustomLayerIds` 后没加载出来 prefab X**

## 步骤 1：确认图层存在且有数据

```bash
python parser.py list-layers <scene>
```

检查：
- 场景里有该动态图层吗？
- layerId 是多少？
- `spatial nodes > 0`？（=0 说明导出阶段就有问题）

## 步骤 2：确认 prefab 已导出到 BlockV2

```bash
python parser.py search-asset <scene> X
```

检查 prefab 在哪个 block、距离哪个图层 asset 最近。

## 步骤 3：检查 asset 字段

```bash
python parser.py query-layer <scene> <layerName>
```

排查路径：

- **如果只有 `AssetType=Collision` 加载出来** → 看 ECS/HIMR 行的 **CLCD**
  - `CLCD=1` 且开启 VG → 等待 VirtualGeometry 类型 asset，但本图层可能没导出 VG → **导出问题或运行时关闭 VG**
  - `CLCD=0` → 应正常加载，检查 LoadDistance 与玩家距离

- 检查 `SceneObjectLevel` 是否在 `s_EnabledSceneObjectLevel` 中（默认 Level1/2/3 都启用）

## 步骤 4：检查 layer_block bitmask

仍排查不出 → 检查 layer_block 是否覆盖该图层（bit 索引对应 `AvailableCustomLayerIds` 的 index）：

```bash
python parser.py query-block layer_block_00_00.bin --scene <scene>
```

# 五、关键数据结构参考

## 5.1 StreamingAssetHeader（ZeroFormatter 序列化）

定义于 `PackageRepo/com.jngame.silk-streaming/Runtime/V2/StreamingHeader.cs:110`

字段顺序紧密排列在 CustomLayerId 之后：

| 偏移（相对 CustomLayerId） | 字段 | 类型 | 说明 |
|---|---|---|---|
| -28 ~ -16 | Bounds.center | Vector3 | 世界坐标中心 |
| -12 ~ 0 | Bounds.extents | Vector3 | 包围盒尺寸 |
| 0 | CustomLayerId | int | 图层 ID |
| 4 | Offset | int | 头表内偏移 |
| 8 | AssetType | short | 资产类型 |
| 10 | SceneObjectLevel | short | 场景物体级别 |
| 12 | LoadDistance | float | 加载距离 |
| 16 | CustomLoadControlData | int | VG 控制位 |

## 5.2 layer_block_00_00.bin entry（121 字节）

| 偏移 | 字段 | 说明 |
|---|---|---|
| 0 | entry_index | entry 序号（0=header） |
| 8 | child_count or 0x7FFFFFFF | header 时为子节点数 |
| 40~48 | center xyz | 节点中心（float×3） |
| 56~64 | extents xyz | 节点尺寸（float×3） |
| 92 | data_offset | 关联数据偏移 |
| 96 | data_size | 关联数据长度 |
| 112 | bitmask | 图层归属位掩码（bit N = AvailableCustomLayerIds[N]） |

## 5.3 运行时过滤逻辑

位于 `StreamingAssetLoaderV2.cs` 的 `CalcDistanceJob`：

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

# 六、实战案例

**问题：** 调用 `SetEnabledCustomLayerIds([-1603526523])` 后，BossFight02 图层的 `Building_Lithos_Print_Floor_07a_coll` 加载出来了，但视觉 mesh 没出来。

**排查路径：**

1. `list-layers` 确认 BossFight02 (layerId=-1603526523) 存在，spatial nodes=76 ✅
2. `search-asset Building_Lithos_Print_Floor_07a` 确认 prefab 在 block_07_08 / block_07_09 中 ✅
3. `query-layer BossFight02` 发现 **4 个 asset：2 个 ECS（CLCD=1）+ 2 个 HIMR（CLCD=0）**

**根因：**

- ECS 类型（mesh 渲染）CLCD=1 → 开启 VG 时被过滤
- HIMR 加载距离 130m，玩家可能超出范围
- Collision 始终加载（与 VG 无关）

**解决方向：**

- 关闭 VG（`VGRenderSettings` disabled）验证 ECS 是否能加载
- 检查 BossFight02 图层有没有导出对应的 VirtualGeometry 类型 asset
- 缩短玩家与目标距离测试 HIMR

# 七、限制与注意

- 解析基于 ZeroFormatter 二进制布局逆向，Silk 版本升级、字段顺序调整需重新校验
- prefab 名提取使用正则 `(Building|Prop|FX|VFX|Env|Anim|Char|NPC)_*`，命名前缀不在此列的资产可能漏报
- `search-asset` 的图层归属基于位置距离推断，存在歧义；以 `query-layer` 的精确字段值为准
- 非 Windows 平台需注意路径分隔符；脚本内部已统一使用 forward slash

# 八、相关代码位置

- `StreamingAssetHeader` 定义：`PackageRepo/com.jngame.silk-streaming/Runtime/V2/StreamingHeader.cs:110`
- `SetEnabledCustomLayerIds`：`PackageRepo/com.jngame.silk-streaming/Runtime/V2/StreamingManager.cs:439`
- `CalcDistanceJob` 过滤逻辑：`PackageRepo/com.jngame.silk-streaming/Runtime/V2/LoadersV2/StreamingAssetLoaderV2.cs:70`
- `StreamingLayerV2` 的 IsAssetAvailable：`PackageRepo/com.jngame.silk-streaming/Runtime/V2/StreamingLayerV2.cs:355`
