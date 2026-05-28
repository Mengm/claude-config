# P0-P5 优化分级规则详细文档

基于包体变体数据 + 材质 keyword 扫描的分级优化规则。

## P0: `multi_compile` → `shader_feature` 候选

### 判定条件

1. **Keyword ratio 在 0.3-0.7 范围**：说明变体未被 strip，on/off 两版都存在
2. **材质使用数 = 0 或极低**：说明运行时大部分变体不会被材质系统选中
3. **影响变体数 ≥ 100**：确保优化收益足够大

### 阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| ratio 下限 | 0.3 | 低于此值已被部分 strip |
| ratio 上限 | 0.7 | 高于此值可能是必需的 |
| 材质使用数上限 | ≤ 1 | 最多 1 个材质使用 |

### 预期收益

- 每个 P0 keyword 改为 `shader_feature` 后，对应变体数减半
- 典型节省：`INSTANCING_ON` 出现在 96 个 shader 中，每个都可减半

### 典型发现（基于 T3 项目）

| Keyword | 影响 Shader 数 | 典型 ratio | 材质使用 |
|---------|---------------|-----------|---------|
| `INSTANCING_ON` | 96 | 0.500 | 0 |
| `_RELATIVE_RENDER` | 57 | 0.3-0.6 | 0 |
| `_SSR` | 31 | 0.500 | 0 |
| `_ADDITIONAL_ADAPTIVE_SHADOWMAP` | 30 | 0.500 | 0 |
| T3Uber: `VIGNETTE`, `BLOOM`, `COLOR_GRADING_COMBINE_LUT2D` 等 | 1 | 0.333-0.500 | 0 |

### 操作指南

```hlsl
// 修改前
#pragma multi_compile _ INSTANCING_ON

// 修改后
#pragma shader_feature_local _ INSTANCING_ON
```

注意：
- 使用 `shader_feature_local` 优于 `shader_feature`（不占用全局 keyword 配额）
- 改动后需确认运行时通过 `Material.EnableKeyword()` 启用的 keyword 仍然生效
- PostProcessing shader 通过代码启用 keyword，需确认不被 strip

---

## P1: 从未使用的 Keyword（ratio = 0）

### 判定条件

1. **Keyword 在所有 pass/stage 中 ratio = 0**：编译变体中从未出现 ON 状态
2. **Keyword 被 shader 声明**：存在于 m_KeywordNames 中

### 阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| ratio | = 0.000 | 所有 pass/stage 均为 0 |

### 预期收益

- 移除声明减少编译开销（不直接减少变体数，但减少编译矩阵复杂度）
- 清理代码噪音

### 典型发现（基于 T3 项目）

| 类别 | 示例 Keyword | 出现 Shader 数 |
|------|-------------|---------------|
| VR/XR | `STEREO_INSTANCING_ON`, `UNITY_SINGLE_PASS_STEREO`, `STEREO_MULTIVIEW_ON`, `STEREO_CUBEMAP_RENDER_ON` | 283 (全部) |
| Platform | `DISABLE_REVERSED_Z` | 282 |
| Debug | `_DEBUG`, `SHADER_API_EDITOR` | 84/47 |
| Editor | `_EDITOR_HLOD_BAKER`, `_USE_UNWRAPED_UV` | 32 |
| VFX 未使用 | `VFX_USE_SEED`, `VFX_USE_TEXINDEX` 等 | 25 |

### 操作指南

1. 确认 keyword 确实无用（检查 C# 代码中是否有 `EnableKeyword` 调用）
2. 从 shader 源码中移除 `#pragma multi_compile`/`shader_feature` 声明
3. 移除对应的 `#if KEYWORD ... #endif` 代码块（或保留默认分支）

---

## P2: VFX Keyword 隔离

### 判定条件

1. **Shader 不属于 VFX 类型**：名称不包含 `Effect/Fx`, `Effect/Particle`, `VFX`
2. **包含大量 `VFX_USE_*` keyword**：≥ 50 个 VFX 前缀的 keyword
3. **VFX keyword 大部分 ratio = 0**：活跃数远小于总数

### 阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| VFX keyword 总数 | ≥ 50 | 存在 VFX 集成 |
| 活跃率 | < 50% | 大部分 VFX keyword 未使用 |

### 预期收益

- 减少 keyword 声明污染
- 降低非 VFX pass 的编译矩阵复杂度

### 典型发现（基于 T3 项目）

| Shader | VFX Keywords | 活跃数 | 总变体 |
|--------|-------------|--------|--------|
| `Environment/Lit` | 213 | 31 | 31,826 |
| `FxCommon` | 265 | 40 | 11,984 |
| `ParticleUniversal` | 233 | 31 | 6,188 |
| `LayeredLitPC` | 214 | 22 | 4,812 |
| `WhiteModelLit` | 213 | 0 | 1,958 |
| `FxUICommon` | 204 | 0 | 272 |

### 操作指南

**方案 A**：VFX pass 改为 `shader_feature_local`
```hlsl
// VFX pass 中
#pragma shader_feature_local VFX_USE_SEED
#pragma shader_feature_local VFX_USE_TEXINDEX
// ...
```

**方案 B**：拆为独立 SubShader
```hlsl
SubShader {
    // 普通渲染 pass（不含 VFX keyword）
    Pass { ... }
}
SubShader {
    Tags { "VFXPass" = "true" }
    // VFX 专用 pass
    Pass { ... }
}
```

---

## P3: T3Uber / PostProcessing 全 `multi_compile` 优化

### 判定条件

1. **PostProcessing uber shader**：名称包含 `PostProcessing`, `T3Uber`, `Uber`
2. **全部 keyword 使用 `multi_compile`**
3. **变体数 > 1000**

### 阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| 变体数 | > 1,000 | 变体组合爆炸 |
| 低使用率 keyword | ratio < 0.3 | 改 shader_feature 目标 |

### 预期收益

| Shader | 当前变体 | 可优化 keyword 数 | 预估优化后 |
|--------|---------|-----------------|-----------|
| T3Uber | 25,920 | ~15/21 | < 2,000 |
| Uber | 9,216 | ~18/23 | < 500 |
| Bloom | 140 | ~8/11 | < 20 |
| TAA | 96 | ~10/12 | < 10 |

### 操作指南

PostProcessing shader 通过 C# 代码动态启用 keyword，因此：
1. 确认哪些 keyword 在运行时通过 `sheet.EnableKeyword()` 启用
2. 被代码启用的 keyword 保持 `multi_compile`
3. 其余改为 `shader_feature`
4. 在 `ShaderVariantCollection` 中预热必需的变体组合

---

## P4: Stripping 规则扩展

### 判定条件

1. **Editor/Debug 专用 keyword**：`_DEBUG`, `SHADER_API_EDITOR`, `_EDITOR_HLOD_BAKER` 等
2. **VR/XR keyword（非 VR 项目）**：`STEREO_*`, `UNITY_SINGLE_PASS_STEREO`
3. **平台特定 keyword（非目标平台）**：`DISABLE_REVERSED_Z`

### 可 strip 的 keyword 列表

| 类别 | Keywords | 出现 Shader 数 |
|------|---------|---------------|
| VR/XR | `STEREO_INSTANCING_ON`, `UNITY_SINGLE_PASS_STEREO`, `STEREO_MULTIVIEW_ON`, `STEREO_CUBEMAP_RENDER_ON` | 283 |
| Platform | `DISABLE_REVERSED_Z` | 282 |
| Debug | `_DEBUG` | 84 |
| Editor | `SHADER_API_EDITOR`, `_EDITOR_HLOD_BAKER`, `_USE_UNWRAPED_UV`, `EDITOR_WRITE_PRIMITIVE_ID` | 31-47 |

### 操作指南

实现 `IPreprocessShaders.OnProcessShader()` 回调：

```csharp
public class ShaderStripping : IPreprocessShaders
{
    static readonly string[] StripKeywords = {
        "STEREO_INSTANCING_ON",
        "UNITY_SINGLE_PASS_STEREO",
        "STEREO_MULTIVIEW_ON",
        "STEREO_CUBEMAP_RENDER_ON",
        "_DEBUG",
        "SHADER_API_EDITOR",
        "_EDITOR_HLOD_BAKER",
    };

    public int callbackOrder => 0;

    public void OnProcessShader(Shader shader, ShaderSnippetData snippet,
        IList<ShaderCompilerData> data)
    {
        for (int i = data.Count - 1; i >= 0; i--)
        {
            foreach (var kw in StripKeywords)
            {
                if (data[i].shaderKeywordSet.IsEnabled(
                    new ShaderKeyword(kw)))
                {
                    data.RemoveAt(i);
                    break;
                }
            }
        }
    }
}
```

---

## P5: 材质 Keyword 死代码

### 判定条件

**孤儿 keyword**：材质启用了 keyword 但 shader binary 中不存在
**无效启用**：keyword 在 shader 中 ratio = 0 但材质仍设置了它

### 典型发现（基于 T3 项目）

| 类别 | 示例 | 材质使用数 |
|------|------|-----------|
| 孤儿 keyword（shader 无声明）| `_USECOLLISION_ON` | 2,289 |
| 孤儿 keyword | `_GREYFORALPHA_ON` | 829 |
| 孤儿 keyword | `_CUSTOMDATA1ZW_ON` | 693 |
| 孤儿 keyword | `_CUSTOMDATA1XY_ON` | 621 |

### 操作指南

批量清理脚本：

```csharp
// Editor 脚本，清理材质中的无效 keyword
[MenuItem("Tools/Clean Orphan Keywords")]
static void CleanOrphanKeywords()
{
    var orphanKeywords = new HashSet<string> {
        "_USECOLLISION_ON", "_GREYFORALPHA_ON",
        "_CUSTOMDATA1ZW_ON", "_CUSTOMDATA1XY_ON"
    };

    var guids = AssetDatabase.FindAssets("t:Material");
    foreach (var guid in guids)
    {
        var path = AssetDatabase.GUIDToAssetPath(guid);
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        bool modified = false;
        foreach (var kw in orphanKeywords)
        {
            if (mat.IsKeywordEnabled(kw))
            {
                mat.DisableKeyword(kw);
                modified = true;
            }
        }
        if (modified) EditorUtility.SetDirty(mat);
    }
    AssetDatabase.SaveAssets();
}
```
