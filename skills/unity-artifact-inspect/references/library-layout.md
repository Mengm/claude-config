# Unity 2022 Library/Artifacts 结构

## 顶层

```
<project>/Library/
├── SourceAssetDB           # LMDB 单文件，guid ↔ assetPath ↔ hash 等
├── SourceAssetDB-lock
├── ArtifactDB              # LMDB 单文件，artifactID ↔ guid+importer 信息
├── ArtifactDB-lock
├── Artifacts/
│   ├── 00/                 # guid 前 2 字符分桶
│   │   ├── 00abc...        # artifact 文件 = guid + importer hash
│   │   ├── 00abc....info   # 附属元数据（可选）
│   │   └── ...
│   ├── 01/
│   ├── ...
│   └── ff/
└── ...
```

## ArtifactDB.cpp 中的关键定义

```cpp
// Modules/AssetDatabase/Editor/V2/ArtifactDB.cpp:51
const char* kArtifactDB = "Library/ArtifactDB";

// Modules/AssetDatabase/Editor/V2/SourceAssetDB.h:74
static const char* kSourceAssetDB = "Library/SourceAssetDB";
```

两者都用 `mdb_env_open` + `MDB_NOSUBDIR`，即单文件 LMDB（非默认的目录式 LMDB）。

## Artifact 文件命名规律

文件名是 64 字符 hex：
- 前 32 字符 = asset 的 GUID（hex 小端表示）
- 后 32 字符 = importer hash（依赖 importer 类型、版本、settings、依赖 asset 的 hash 等）

同一个 asset 在 importer settings 变化、依赖变化、importer 版本升级时会生成多个 artifact。
Unity 通过 ArtifactDB 跟踪"当前 current"是哪个，但磁盘上历史 artifact 不会立即删除（依赖
EditorAssetGarbageCollectManager）。

**简化推断当前 artifact** = 同 guid 下 mtime 最新的文件。

## .meta 文件

每个 import 过的 asset 在源文件旁边有 `.meta`，YAML 格式：

```yaml
fileFormatVersion: 2
guid: a1b2c3d4e5f67890abcdef1234567890
TextureImporter:
  ...
```

guid 提取：`grep -m1 '^guid: ' file.meta | awk '{print $2}'`。
