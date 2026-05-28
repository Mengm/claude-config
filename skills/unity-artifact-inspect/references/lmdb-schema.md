# LMDB Schema —— 完全解码（已对 Unity 2022.3 源码 + 真实项目验证）

Unity 的 AssetDatabase V2 用标准 OpenLDAP LMDB（`External/LMDB`，v0.9.18）存索引。
本文档记录从 `guid` 解析到磁盘 artifact 文件的完整链路，全部已实证。

## 工具：unity_lmdb_dump.exe

源码 `bin/unity_lmdb_dump.c`，链接 Unity 自带 `External/LMDB/{mdb.c,midl.c}`，
用 MSVC 编译（`bin/build-mdb_dump.bat`）。零外部依赖（不需要 pip lmdb / mdb_dump）。

```
unity_lmdb_dump.exe <env-file> <subdb-name>
```
- 以 `MDB_NOSUBDIR | MDB_RDONLY | MDB_NOLOCK` 打开（Unity 用单文件 LMDB；NOLOCK 让我们能在 Editor 运行时并发只读）
- 输出每条 entry 两行：`K <hex-key>` / `V <hex-value>`
- 实测 50 万条 entry 约 2-4s

## 数据库与 sub-DB

```
Library/SourceAssetDB   (LMDB env)
  ├── GuidToPath        key=guid(16B)        value=assetPath(ASCII, null-term)
  ├── PathToGuid
  ├── GuidToIsDir / GuidToChildren / GuidPropertyIDToProperty
  ├── RootFolders / Misc / PropertyIDToType
  └── hash              (HashDB: path -> hash)

Library/ArtifactDB      (LMDB env)
  ├── ArtifactKeyToArtifactIDs       key=Hash128(GetArtifactDBKey)  value=ArtifactIDs blob
  ├── ArtifactIDToArtifactMetaInfo   key=artifactID(16B)            value=ArtifactMetaInfo blob ★
  ├── ArtifactIDToArtifactDependencies
  ├── ArtifactIDPropertyIDToProperty
  ├── ArtifactIDToImportStats
  └── CurrentRevisions               value 含 guid + 当前 artifactID  ★
```

源码：`Modules/AssetDatabase/Editor/V2/{GuidDB,ArtifactDB,SourceAssetDB,HashDB}.cpp`

## ★ 关键编码：GUID 的 nibble-swap

`.meta` 文件里的 guid hex 与 LMDB 中存的字节**每个 byte 的两个 nibble 交换**。

```
.meta:  22618ec154bb2634ebbcd1e5ed28af15
LMDB:   2216e81c45bb6243becb1d5ede82fa51   (每字节 AB->BA)
```

原因：`GUIDToString`（Runtime/Utilities/GUID.cpp）按 `name[i*8+j] = (data[i]>>(j*4))&0xF`，
j 从 7→0，使得字符串里每字节低 nibble 在前。bash 实现：

```bash
swap_nibbles() { local s=$1 out="" i; for ((i=0;i<${#s};i+=2)); do out="$out${s:$((i+1)):1}${s:$i:1}"; done; echo "$out"; }
```

ArtifactID / contentHash 用 `Hash128ToString`（标准 byte-wise hex，**不** swap）。

## ★ 完整链路：guid → 磁盘 artifact 文件

```
.meta guid
  │  swap_nibbles
  ▼
LMDB guid bytes
  │  CurrentRevisions: 找 value[0:16]==guid 的那条；artifactID = value 末 16 字节
  ▼
artifactID  (Hash128)
  │  ArtifactIDToArtifactMetaInfo[artifactID] -> ArtifactMetaInfo blob
  │  从 blob 的 producedFiles[].contentHash 取磁盘文件名
  ▼
contentHash (Hash128, byte-wise hex)
  ▼
Library/Artifacts/<contentHash[0:2]>/<contentHash>
```

**磁盘文件名 = producedFile 的 contentHash，不是 artifactID。**
（`ArtifactInfo.cpp::InitializeProducedFiles` → `GetHashedContentPath(contentHash)`
→ `ArtifactPath.cpp::FilePathFromHash`）

一个 guid 可能有多个 artifactID（不同 importer 变体）；`CurrentRevisions` 给出当前生效的那个。

## Value 二进制布局（实测）

### CurrentRevisions value（64 bytes）
```
[0:16]   guid (nibble-swapped)
[16:48]  BlobImporterID  (nativeImporterType 4B = ffffffff 表无 + scriptedImporterType 16B + padding)
[48:64]  artifactID (Hash128)
```
guid 在**开头**。

### ArtifactIDToArtifactMetaInfo value（变长，本例 365 bytes）
对应 `struct ArtifactMetaInfo`（ArtifactMetaInfo.h）：
```
[0:16]   artifactMetaInfoHash (Hash128)
[16:32]  artifactKey.guid (nibble-swapped)        ← guid 在 byte 16
[32:36]  artifactKey.importerID.nativeImporterType
[36:52]  artifactKey.importerID.scriptedImporterType
[52:...] type / isImportedAssetCacheable / BlobArray<ArtifactFileMetaInfo> producedFiles ...
         producedFiles 里每个 ArtifactFileMetaInfo 含 Hash128 contentHash
```
BlobArray/BlobString 是相对偏移指针（`BlobOffsetPtr.m_Offset = ptr - this`），手算偏移脆弱。

**稳健提取策略（脚本采用）**：不解 blob 偏移，直接扫 value 的所有 16-byte 窗口，
凡能映射到 `Library/Artifacts/<x>/<window>` 且文件存在的，即为 producedFile 的 contentHash。
material 通常 1 个产出文件，texture/fbx 可能多个（主数据 + meta）。

## 注意事项

- **LMDB 与磁盘可能不完全同步**：Project-T3 实测 728k 磁盘 artifact vs 518k LMDB entry。
  有的 LMDB 记录指向已 GC 的 contentHash（文件不存在）——脚本只输出磁盘真实存在的。
- **artifactID ≠ 磁盘文件名**：早期 v2 文档误以为文件名是 guid 或 artifactID，均错。
- Editor 运行时持 `*-lock`，但 `MDB_NOLOCK` 只读不受影响。

## 源码索引

- guid 编码: `Runtime/Utilities/GUID.cpp` GUIDToString / StringToGUID
- artifactID hex: `Runtime/Utilities/Hash128.cpp` Hash128ToString
- DB key 生成: `ArtifactDB.cpp` GetArtifactDBKey (HashGenerator feed guid+importerID)
- sub-DB 名: `ArtifactDB.cpp:194-199`, `GuidDB.cpp:51-58`
- contentHash→路径: `ArtifactPath.cpp` FilePathFromHash:51 / GetHashedContentPath:106
- producedFiles: `ArtifactInfo.cpp` InitializeProducedFiles:460 / `ArtifactMetaInfo.h` struct
