---
name: unity-artifact-inspect
description: 查询 Unity project 中 asset 的引用关系、Library artifact 文件、用 binary2text 转出可读文本。触发场景 (1) "xxx.mat / xxx.prefab / xxx.fbx 引用了哪些资源" / "依赖关系" (2) "看 xxx.fbx import 后是什么样" / "binary2text 这个资源" (3) "这个 Library 文件是哪个 asset" / "反查 artifact" (4) 用户提供 .meta、.mat/.prefab/.fbx/.png 文件、Library/Artifacts 路径、或 Unity project 根目录。即使没明确说 "binary2text"，只要意图是查 import 产物或资源引用都应触发。
---

# Unity Artifact Inspect

不打开 Unity Editor，就能查清 asset 的引用关系、找到它 import 后在 Library 的文件、把二进制 import 产物转成可读文本。全程**只读**，Editor 开着也能用。

## 入口：unity_artifact.py

一个统一 CLI，四个子命令：

```bash
PY=~/.claude/skills/unity-artifact-inspect/unity_artifact.py
PROJ="F:/Perforce/Project-T3-baiyuan/client"   # Unity 工程根（含 Assets/ 和 Library/）

python "$PY" refs    "$PROJ" <guid|asset>            # 查引用（最常用）
python "$PY" resolve "$PROJ" <guid|asset>            # guid -> 磁盘 artifact 文件
python "$PY" inspect "$PROJ" <guid|asset>            # asset -> binary2text 文本
python "$PY" index   "$PROJ"                         # 重建 guid->asset 索引（一般自动）
```

target 可以是 32 位 guid、asset 相对/绝对路径、或 .meta 路径。
Windows + Git Bash 下若输出中文乱码，先 `export PYTHONIOENCODING=utf-8`。

## 一次性准备

`resolve` / `inspect` / 二进制 `refs` 依赖底层 LMDB 读取工具（从 Unity 自带 LMDB 源码编译，零外部依赖）：

```cmd
bin\build-mdb_dump.bat
```

产物 `bin/unity_lmdb_dump.exe`，**只需编译一次**，所有项目复用。需要 MSVC（脚本自动调 vcvars64.bat）。
为什么不用纯 Python 读 LMDB：LMDB 的磁盘 page 格式是私有二进制结构，纯 Python 逆向不现实且易错；
而 Unity 自带 `External/LMDB` 的 C 源码，自编译既零依赖又与 Unity 写入时版本绝对一致。Python 只接管
dump *之上* 的解析。

## 子命令说明

### refs — 查引用 ⭐
- **文本 YAML**（.mat/.prefab/.asset/.scene…）：直接读源文件的 `guid:`
- **二进制**（.fbx/.png/.tga…）或纯 guid：经 LMDB 找 artifact → binary2text → 提取 `GUID:` 引用
- 输出每个引用 guid → asset 路径，标 `<builtin>`（内置，guid 前 8 位全 0）/ `<not found>`（已删除或残留引用）

```
=== .../M_Rock.mat 引用 12 个外部 guid ===
(self guid: 22618ec154bb2634ebbcd1e5ed28af15)
  00aca33abddc3f24ab5389f152b6dbd7  ->  Assets/.../Common_Rock_23a_d.tga
  97fc7131a7af2bd42987997ac63b7a16  ->  <not found>
Summary: 11 resolved / 0 builtin / 1 not found
```

### resolve — guid → 磁盘 artifact 文件
输出 `<contentHash>\t<文件路径>\t<字节数>`，一行一个产出文件。

### inspect — asset → binary2text 文本
经 `resolve` 找到真实 artifact（不靠猜文件名），`binary2text -detailed` 转文本，
写到 `<project>/Temp/unity-artifact-skill/<name>.<contentHash8>.txt`，返回路径。
binary2text.exe 解析顺序：`--bin2text` > `UNITY_BINARY2TEXT` > 工程同盘 Unity Hub > fallback jnunity 仓库构建产物。

### index — 重建 guid 索引
扫 Assets+Packages+PackageCache 的 .meta。首次/24h 过期会自动重建，一般不用手动跑。

## 工作原理

guid → 磁盘 artifact 完整链路（对 Unity 2022.3 源码逐字节验证）：
```
.meta guid --每字节 nibble 交换--> LMDB guid
  --CurrentRevisions--> 当前 artifactID
  --ArtifactIDToArtifactMetaInfo--> producedFiles[].contentHash
  --> Library/Artifacts/<ch[:2]>/<contentHash>
```
**磁盘文件名 = producedFile 的 contentHash，不是 artifactID 也不是 guid。**
guid 在 .meta（`22618ec1…`）和 LMDB（`2216e81c…`）里是每字节高低 nibble 交换的关系。
`unity_lmdb_dump.exe` 用 `MDB_NOLOCK` 只读打开，Editor 运行时不冲突。
详见 `references/lmdb-schema.md`。

## 性能（实测 49 万资产工程）
- guid 索引首次构建：≈ 几分钟（Python rglob 全量扫 .meta）
- LMDB dump：CurrentRevisions 2s / ArtifactMetaInfo ≈ 27s，缓存 24h
- 命中缓存后 resolve / inspect / refs 秒级

## 注意事项
- **material 的 artifact 只是 importer 元数据**（NativeFormatImporter）。文本 YAML 资产真实内容在源文件，看 refs / 源文件即可。
- **贴图/模型 artifact 含真实导入产物**：尺寸、格式（BC7/BC5…）、mipmap、像素数据。
- **LMDB 与磁盘可能不完全同步**：resolve 只输出磁盘真实存在的文件（指向已 GC contentHash 的记录跳过）。

## 文件结构
```
unity-artifact-inspect/
├── SKILL.md
├── unity_artifact.py           # ★ 统一 CLI：index / resolve / inspect / refs
├── bin/
│   ├── unity_lmdb_dump.c       # LMDB sub-DB dumper 源码
│   ├── build-mdb_dump.bat      # MSVC 编译脚本
│   └── unity_lmdb_dump.exe     # 编译产物（首次运行 .bat 生成）
└── references/
    ├── library-layout.md       # Library/Artifacts 结构
    ├── binary2text-output.md   # binary2text 输出格式 + guid 正则
    └── lmdb-schema.md          # 完整 LMDB schema + guid→artifact 链路
```
