# JNFS + Unity 二进制格式技术参考

## JNFS 包格式

JNFS（JN File System）是 JN 引擎自定义的资源归档格式，由 `.idx`（索引文件）+ `.data`（数据文件）组成。

### IDX 文件结构

所有整数均为大端序（Big-Endian）。

```
┌─────────────────────────────────────────────┐
│ Header                                       │
│   fileEntryCount  (U32 BE)                   │
│   dataEntryCount  (U32 BE)                   │
├─────────────────────────────────────────────┤
│ DataEntry[dataEntryCount] (28 bytes each)    │
│   contentHash     (16 bytes, MD5)            │
│   offset          (U32 BE) → .data 中的偏移  │
│   encodedSize     (U32 BE) → 压缩后大小      │
│   decodedSize     (U32 BE) → 解压后大小      │
├─────────────────────────────────────────────┤
│ FileEntry[fileEntryCount] (24 bytes each)    │
│   pathHash        (U64 BE) → 文件路径 hash   │
│   contentHash     (16 bytes) → 关联 DataEntry │
└─────────────────────────────────────────────┘
```

**关联逻辑**：FileEntry.contentHash → DataEntry.contentHash，建立路径到数据的映射。

### DATA 文件结构

DATA 文件是连续存放的压缩数据块。每个 DataEntry 的 `offset` 指向 DATA 文件中的起始位置，读取 `encodedSize` 字节后解压。

数据块可能是：
1. **裸 SerializedFile 数据**（无 JNTE 容器）
2. **JNTE 压缩容器**（需先解压再解析）

判断方法：读取前 4 字节，若为 `0x4A4E5445` ('JNTE') 则是 JNTE 容器。

---

## JNTE 压缩容器

JNTE 是 JN 引擎的多块压缩容器格式。

### 结构

```
┌─────────────────────────────────────────────┐
│ Header                                       │
│   signature    (U32 BE = 0x4A4E5445 'JNTE')  │
│   chunkCount   (U32 BE)                      │
├─────────────────────────────────────────────┤
│ ChunkInfo[chunkCount] (9 bytes each)         │
│   type             (U8)                      │
│     0 = Raw (无压缩)                          │
│     1 = LZ4                                  │
│     2 = LZMA                                 │
│     3 = Zstd (需 XOR 还原)                    │
│   decompressedSize (U32 BE)                  │
│   compressedSize   (U32 BE)                  │
├─────────────────────────────────────────────┤
│ ChunkData[]                                  │
│   chunk[0] data (compressedSize[0] bytes)    │
│   chunk[1] data (compressedSize[1] bytes)    │
│   ...                                        │
└─────────────────────────────────────────────┘
```

解压后将所有 chunk 的数据拼接即为完整的 SerializedFile。

---

## XOR 混淆还原（Zstd 专用）

JN 引擎修改了 zstd 帧格式以防止直接解压。修改了两处：

### 1. Magic Number 替换

```
标准 zstd magic:  0xFD2FB528
JN 替换 magic:    0xFA4BF25C
```

这不是 XOR，而是直接在 `zstd.h` 中替换了常量。还原时直接写回标准值。

### 2. Frame Header 字段 XOR

JN 引擎在 `mem.h` 中定义了 `_jn` 系列读写函数，对以下字段应用 XOR：

| 字段 | 条件 | XOR 常量 |
|------|------|---------|
| Dictionary ID (2B) | dict_id_size_code = 2 | `0x4A4E` (U16) |
| Dictionary ID (4B) | dict_id_size_code = 3 | `0x4A4E5445` (U32) |
| Frame Content Size (2B) | fcs_id = 1 | `0x4A4E` (U16) |
| Frame Content Size (4B) | fcs_id = 2 | `0x4A4E5445` (U32) |
| Frame Content Size (8B) | fcs_id = 3 | `0x637c777bf26b6fc5` (U64) |

**注意**：
- 1 字节字段不做 XOR（无 `_jn` 变体）
- Block data 不受影响，仅 frame header 被修改
- Window descriptor 不做 XOR

### 还原流程

```python
def fix_zstd_xor(data: bytes) -> bytes:
    buf = bytearray(data)

    # 1. 检查 magic
    magic = struct.unpack_from('<I', buf, 0)[0]
    if magic != 0xFA4BF25C:  # 非 JN magic，跳过
        return data

    # 2. 替换 magic
    struct.pack_into('<I', buf, 0, 0xFD2FB528)

    # 3. 解析 frame header descriptor (byte 4)
    fhd = buf[4]
    dict_id_size_code = fhd & 0x03
    single_segment = (fhd >> 5) & 1
    fcs_id = fhd >> 6

    pos = 5
    if not single_segment:
        pos += 1  # skip window descriptor

    # 4. XOR dictionary ID
    dict_id_sizes = {0: 0, 1: 1, 2: 2, 3: 4}
    dict_id_size = dict_id_sizes[dict_id_size_code]
    if dict_id_size == 2:
        val = struct.unpack_from('<H', buf, pos)[0] ^ 0x4A4E
        struct.pack_into('<H', buf, pos, val)
    elif dict_id_size == 4:
        val = struct.unpack_from('<I', buf, pos)[0] ^ 0x4A4E5445
        struct.pack_into('<I', buf, pos, val)
    pos += dict_id_size

    # 5. XOR Frame Content Size
    if fcs_id == 1:
        val = struct.unpack_from('<H', buf, pos)[0] ^ 0x4A4E
        struct.pack_into('<H', buf, pos, val)
    elif fcs_id == 2:
        val = struct.unpack_from('<I', buf, pos)[0] ^ 0x4A4E5445
        struct.pack_into('<I', buf, pos, val)
    elif fcs_id == 3:
        val = struct.unpack_from('<Q', buf, pos)[0] ^ 0x637c777bf26b6fc5
        struct.pack_into('<Q', buf, pos, val)

    return bytes(buf)
```

---

## UnityFS 包格式

标准 Unity AssetBundle 格式（`data.unity3d` 等文件）。

### Header

```
┌─────────────────────────────────────────────┐
│ magic         (null-terminated: "UnityFS")    │
│ version       (U32 BE)                        │
│ unity_version (null-terminated string)        │
│ generator_ver (null-terminated string)        │
│ file_size     (U64 BE)                        │
│ compressed_block_size   (U32 BE)              │
│ uncompressed_block_size (U32 BE)              │
│ flags         (U32 BE)                        │
│   [0:5]  compression type (0=none,1=LZMA,2/3=LZ4) │
│   [6]    has directory info                   │
│   [7]    blocks at end of file                │
│   [9]    padding at start (align to 16)       │
└─────────────────────────────────────────────┘
```

### Block Info（解压后）

```
┌─────────────────────────────────────────────┐
│ data_hash     (16 bytes)                     │
│ block_count   (U32 BE)                       │
│ BlockStorageInfo[block_count]:               │
│   uncompressed_size (U32 BE)                 │
│   compressed_size   (U32 BE)                 │
│   flags             (U16 BE)                 │
│     [0:5] compression (0=none,2/3=LZ4,1=LZMA) │
│ node_count    (U32 BE)                       │
│ DirectoryInfo[node_count]:                   │
│   offset   (U64 BE) → 解压数据中的偏移       │
│   size     (U64 BE) → 数据大小               │
│   flags    (U32 BE)                          │
│   name     (null-terminated string)          │
└─────────────────────────────────────────────┘
```

解压所有 Block 后拼接，再按 DirectoryInfo 的 offset/size 切片得到各 SerializedFile。

---

## Unity SerializedFile 格式

### Header（始终大端序）

```
┌─────────────────────────────────────────────┐
│ metadata_size  (U32 BE)                      │
│ file_size      (U32 BE)                      │
│ version        (U32 BE)  — 通常 17-22        │
│ data_offset    (U32 BE)                      │
│ endianness     (U8)      — v9+               │
│ reserved       (3 bytes)                     │
│ [v22+ Extended Header, still BE]:            │
│   metadata_size (U32)                        │
│   file_size     (I64)                        │
│   data_offset   (I64)                        │
│   unknown       (I64)                        │
└─────────────────────────────────────────────┘
```

v9+ 之后 metadata 使用文件自声明的端序（`endianness` 字段）。

### Metadata（使用文件端序）

```
┌─────────────────────────────────────────────┐
│ unity_version (null-terminated, v7+)         │
│ target_platform (U32, v8+)                   │
│ enable_type_tree (U8, v13+)                  │
│ type_count (U32)                             │
│ SerializedType[type_count]:                  │
│   class_id    (U32 for v17+, I16 for older)  │
│   is_stripped  (U8, v16+)                    │
│   script_type_index (I16, v17+)              │
│   [Hash128 fields for v13+]                  │
│   [TypeTree blob if enabled]                 │
│ object_count (U32)                           │
│ ObjectInfo[object_count]:                    │
│   [align4, v14+]                             │
│   path_id     (I64 for v14+)                 │
│   byte_start  (I64 for v22+, U32 otherwise)  │
│   byte_size   (U32)                          │
│   type_id     (U32) → index into types[]     │
└─────────────────────────────────────────────┘
```

### 定位 Shader 对象

1. 遍历 types[]，找到 `class_id == 48` (Shader) 的 type index
2. 遍历 objects[]，找到 `type_id` 匹配的条目
3. 使用 `data_offset + byte_start` 定位对象数据，读取 `byte_size` 字节

---

## SerializedShader 二进制布局

Shader 对象数据按 `Transfer()` 顺序排列的字段。

### 字段顺序（完整）

```
NamedObject.m_Name         (String: U32 len + chars + align4)

m_ParsedForm (SerializedShader):
  m_PropInfo (SerializedProperties):
    m_Props[] (Array<SerializedProperty>):
      each: m_Name(String) + m_Description(String)
            + m_Attributes[](Array<String>)
            + m_Type(I32) + m_Flags(U32)
            + m_DefValue[4](16B)
            + m_DefTexture: m_DefaultName(String) + m_TexDim(I32)

  m_SubShaders[] (Array<SerializedSubShader>):
    each:
      m_Passes[] (Array<SerializedPass>):
        each:
          m_EditorDataHash[] (Array<Hash128>)
          m_Platforms[] (Array<U8>)
          m_NameIndices (Map<String,I32>)
          m_Type (I32)
          m_State (SerializedShaderState):  ← 大量固定字段
            m_Name(String)
            rtBlend[8] × 7 FloatValue
            rtSeparateBlend(bool) + align4
            8 × FloatValue (zClip..alphaToMask)
            3 × StencilOp (4 FloatValue each)
            3 × FloatValue (stencilReadMask..Ref)
            3 × FloatValue (fogStart..Density)
            fogColor (VectorValue = 4 FloatValue + name)
            fogMode(I32) + gpuProgramID(I32)
            m_Tags(Map<String,String>)
            m_LOD(I32) + lighting(bool+align4)
          m_ProgramMask (U32)
          m_Programs[6] (Vertex/Fragment/Geometry/Hull/Domain/RayTracing):
            each SerializedProgram:
              m_SubPrograms[] (old format)
              m_PlayerSubPrograms[][] (new: per-tier arrays)  ← 每个=一个变体
              m_ParameterBlobIndices[][] (Array<Array<U32>>)
              m_CommonParameters (ProgramParameters)
              m_SerializedKeywordStateMask[] (Array<U16>)
              m_UserGlobal/Local/Builtin[] (Array<String>)
          m_HasInstancingVariant(bool)
          m_HasProceduralInstancingVariant(bool) + align4
          m_UseName(String) + m_Name(String) + m_TextureName(String)
          m_Tags(Map<String,String>)
      m_Tags(Map<String,String>)
      m_LOD(I32)

  m_KeywordNames[]  (Array<String>)       ← keyword 名称列表
  m_KeywordFlags[]  (Array<U8>, 可选)     ← 0=multi_compile, 1=shader_feature 等
  m_Name            (String)              ← 真正的 shader 名称
  m_CustomEditorName (String)
  m_FallbackName     (String)
  ...
```

### SerializedPlayerSubProgram（变体）

```
┌─────────────────────────────────────────────┐
│ m_BlobIndex       (U32) → 编译后字节码索引   │
│ m_KeywordIndices  (Array<U16>: I32 count     │
│                    + U16[] + align4)          │
│                    → 此变体启用的 keyword 索引 │
│ m_ShaderRequirements (U64) → GPU 特性要求    │
│ m_GpuProgramType  (U8 enum + align4)         │
│                    → 目标 GPU API             │
└─────────────────────────────────────────────┘
```

### FloatValue / VectorValue / StencilOp

```
SerializedShaderFloatValue:
  val  (float, 4B)
  name (String: FastPropertyName, serialized as string)

SerializedShaderVectorValue:
  x, y, z, w (4 × FloatValue)
  name       (String)

SerializedStencilOp:
  4 × FloatValue (pass, fail, zFail, comp)

SerializedShaderRTBlendState:
  7 × FloatValue (srcBlend, destBlend, srcAlpha, destAlpha, blendOp, alphaOp, colorMask)
```

### Keyword Ratio 计算

对某个 shader 中特定 (pass, stage) 的变体集：

```
total_variants = len(player_sub_programs)

for each keyword K at index i:
    on_count = count of variants where i ∈ variant.keyword_indices
    ratio = on_count / total_variants
```

ratio 解读：
- `0.0`：keyword 已被 strip，所有变体均为 OFF
- `0.5`：keyword 未被 strip，ON/OFF 各占一半（`multi_compile` 典型）
- `1.0`：keyword 总是 ON（可硬编码）
- `0.333`：keyword 与其他 keyword 互斥（如 3 选 1 的 `multi_compile A B C`）
