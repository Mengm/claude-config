# LMDB Schema (扩展锚点，第一版未实现)

## 文件位置

- `<project>/Library/SourceAssetDB` — guid ↔ assetPath、metaFileHash、source hash 等
- `<project>/Library/ArtifactDB` — artifactID ↔ guid + importer 信息 + dependencies

两者都用 `mdb_env_open(env, path, MDB_NOSUBDIR, 0777)`，即**单文件 LMDB**（非默认的目录模式）。

## Schema 来源

引擎源码位置：
- `Modules/AssetDatabase/Editor/V2/SourceAssetDB.cpp`
- `Modules/AssetDatabase/Editor/V2/SourceAssetDB.h`
- `Modules/AssetDatabase/Editor/V2/ArtifactDB.cpp`
- `Modules/AssetDatabase/Editor/V2/ArtifactDB.h`

第一版若要实现 LMDB 直读，需要：

1. 用 `python -m lmdb` 或 `mdb_dump` 把数据库 dump 成可解析格式
2. 按上面的 .cpp/.h 文件中的 `SerializedFile` / `BlobWrite` 调用确认 key/value 二进制布局
3. 处理 Editor 持有写锁时的读阻塞（用 `MDB_NOLOCK` + `MDB_RDONLY` 打开 dump 工具）

## 已知约束

- Unity Editor 运行时持有 `SourceAssetDB-lock` 文件，外部 LMDB reader 需要 RDONLY+NOLOCK 才能并发读
- ArtifactDB 的 value 大概率是引擎自己的 `SerializedFile` 格式 blob，纯 Python 反序列化复杂度高
- 简单替代：让 Unity Editor 通过 menu / cmdline 导出 ArtifactDB 内容到 json，再由 skill 解析

## 何时考虑实现

当 `.meta` 扫描方案的性能瓶颈或语义缺失变得明显时再做：

- 项目 .meta 数 > 50k，扫描超过 30s
- 用户需要 "current artifact" 精确判定（不能用 mtime 近似）
- 用户需要 import 依赖图（artifact 依赖哪些其他 artifact）
