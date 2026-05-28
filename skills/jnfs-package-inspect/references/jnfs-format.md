# JNFS 二进制格式参考

## 文件布局

JN 引擎的 JNFS 归档由 `.idx`（索引）+ `.data`（内容）成对出现，命名形如：

```
res/<lang>/<phase>/data.<n>.idx
res/<lang>/<phase>/data.<n>.data
```

例如：`res/common/gameplay/data.7.idx` + `res/common/gameplay/data.7.data`。

`.idx` 文件结构（全部大端序）：

```
Header (8 B):
  fileEntryCount   U32 BE
  dataEntryCount   U32 BE

DataEntry[dataEntryCount]  (28 B each):
  contentHash      16 B    # MD5
  offset           U32 BE  # offset into .data
  encodedSize      U32 BE  # 压缩后大小
  decodedSize      U32 BE  # 解压后大小

FileEntry[fileEntryCount]  (24 B each):
  pathHash         U64 BE  # 原始路径 hash, 单向不可逆
  contentHash      16 B    # 引用 DataEntry.contentHash
```

## 关键观察

### 1. `fileEntryCount` 通常 ≥ `dataEntryCount`

多个 FileEntry 可以指向同一个 DataEntry（去重）。所以：
- "包内文件数量" 用 `fileEntryCount`
- "唯一内容块数量" 用 `dataEntryCount`

### 2. pathHash 不可逆

FileEntry 只存 8 字节 hash，没有原始路径字符串。所以**离开 manifest，包体内部任何资产名都拿不回来**。这是 skill 选择 manifest 作为权威路径表的根本原因。

### 3. contentHash 是 join key

manifest JSON 里的 `Hash` 字段（32-char hex）就是 `DataEntry.contentHash` 的 hex 编码。所以验证一个 manifest 完整性的最快办法：

```python
manifest_hashes = {e["Hash"].lower() for e in manifest}
jnfs_hashes     = {de.content_hash.hex() for idx in all_idx for de in read_idx(idx)[0]}
diff = manifest_hashes - jnfs_hashes   # manifest 声称但 JNFS 里找不到的资产
```

## .data 内容容器

`.data` 中每个 DataEntry 范围的内容多数是 **JNTE** 容器（JN engine compression wrapper），但**不是所有 blob 都包 JNTE**——某些已经是流式数据（SVT `.gtp`、`.gts`）会以裸字节直接落地，或带自定义 magic（如 `GRAP`）。

JNTE 容器格式：

```
Header (8 B):
  signature   U32 BE = 0x4A4E5445  ('JNTE')
  chunkCount  U32 BE

ChunkInfo[chunkCount] (9 B each):
  type            U8   # 0=Raw, 1=LZ4, 2=LZMA, 3=Zstd
  decompSize      U32 BE
  compSize        U32 BE

ChunkData[]:
  压缩字节流
```

JN 引擎对 zstd 做了 magic 替换：`0xFD2FB528` → `0xFA4BF25C`（直接改，没 XOR）。如果要解压它的 zstd chunk，要先把前 4 字节 magic 改回标准。

## Manifest 字段（PathProvider 视角）

manifest JSON 是 JN 引擎打包流水线的产物，每条记录在客户端 `IPathProvider` 里都是一条可解析的路径条目：

| 字段 | 类型 | 说明 |
|---|---|---|
| `AssetPath` | string | Unity 项目内 `Assets/...` 路径。流式资源（SVT、addressable group 等）此字段可能为空 |
| `Index` | int | 同一资产多版本时的子索引（一般为 0） |
| `Hash` | hex string | MD5；与 JNFS DataEntry.contentHash hex 一致 |
| `AssetLevel` | int | 加载等级（base=0 等） |
| `GroupId` | int | 业务分组 |
| `InternalPath` | string | JNFS 内部小写 hash 路径，如 `jnfs/gui/startup/start.prefab` 或 `svt/<guid>.gts` |
| `PackageTag` | string | 业务分包标签（base/gameplay 等） |
| `DiskPath` | string | 构建机原始落地路径（来自 Jenkins 工作区） |
| `DiskFilePath` | string | 同上但加上 hash 子目录 |
| `DiskFileMd5` | string | 与 Hash 一致 |
| `FileSize` | int | 原始字节数（未压缩） |

> 注意 `InternalPath` 在 manifest 一定有值，`AssetPath` 不一定有。所以分桶时优先 `InternalPath`，回退 `AssetPath`。

## 一致性 sanity check

跑 skill 之前/之后可以快速验证：

```text
manifest 总条目数 == sum(fileEntryCount) over all .idx files
```

不一致说明 manifest 与包体不匹配（典型原因：发版后 manifest 没刷新，或拿到的是不同 channel 的 manifest）。
