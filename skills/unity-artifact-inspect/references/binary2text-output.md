# binary2text 输出格式

## CLI

```
Usage: binary2text inputbinaryfile [outputtextfile] [-detailed] [-largebinaryhashonly] [-hexfloat]
```

- 不带 `outputtextfile` → 写到 stdin 同名 `.txt`
- `-detailed` → 展开嵌套字段、含 PPtr 信息（refs 解析依赖此模式）
- `-largebinaryhashonly` → 对大块二进制（mesh data 等）只输出 hash
- `-hexfloat` → float 用 hex 表示，便于精确对比

## 典型输出片段（Material asset）

```
ExternalReferences
    PathWithMetaExtension Library/unity default resources
        Guid 0000000000000000e000000000000000
        Type 0
    PathWithMetaExtension Assets/Textures/wood.png
        Guid a1b2c3d4e5f67890abcdef1234567890
        Type 3
...
Material Base
    m_ObjectHideFlags 0
    m_CorrespondingSourceObject  PPtr<Object>
        m_FileID 0
        m_PathID 0
    m_Shader  PPtr<Shader>
        m_FileID 2
        m_PathID 46
    m_SavedProperties SerializedProperties
        m_TexEnvs  vector
            data  pair
                first  FastPropertyName
                    name "_MainTex"
                second  TexEnv
                    m_Texture  PPtr<Texture>
                        m_FileID 3
                        m_PathID 2800000
```

## refs 提取策略

`-detailed` 模式下，外部资源引用通过两个步骤还原：

1. **ExternalReferences 段**：开头列出所有外部文件的 `(FileID → guid + type)` 映射
2. **PPtr 段**：每个 `m_FileID N` + `m_PathID M` 表示引用 ExternalReferences 表第 N 项的对象（PathID = LocalFileIdentifier）

简化提取（第一版只关心 guid 集合）：

```bash
# 注意：本仓库的 binary2text 在 External References 段用大写带冒号 "GUID: <hex>"
#   path(1): "" GUID: 249c86c68ea47504daf0d1e64b7df9db Type: 2
# 兼容两种写法（大写 GUID: 与小写 guid:）：
grep -hoiE 'guid:? [0-9a-f]{32}' <txt> | grep -oE '[0-9a-f]{32}' | sort -u
```

这会拿到所有 ExternalReferences 段里的 guid，等价于"该 asset 引用的所有外部 asset 的 guid 集合"。
不区分实际使用 vs 仅声明，但已足够回答 "这个 prefab 用了哪些资源"。

## 内置/默认资源识别

- `0000000000000000e000000000000000` → unity default resources
- `0000000000000000f000000000000000` → unity builtin extra
- `0000000000000000c000000000000000` → unity_builtin_extra（旧版别名）
- 前 8 字符 `00000000` → 几乎都是内置资源

refs 输出时把这些标记为 `<builtin>`，不去 .meta 索引里查（查不到）。
