---
name: unity-artifact-inspect
description: 查询 Unity project 中 asset 的 Library artifact 文件、用 binary2text 转出可读文本、解析资源引用。触发场景 (1) 用户问 "xxx.fbx import 后是什么样" / "binary2text 这个资源" (2) "这个 Library 文件是哪个 asset" / "反查 artifact" (3) "这个 prefab 引用了哪些资源" / "依赖关系" (4) 用户提供 .meta 文件、Library/Artifacts 路径、或 Unity project 根目录。即使没明确说 "binary2text"，只要意图是查 import 产物或资源引用都应触发。
---

# Unity Artifact Inspect

把 Unity project 的 Library artifact 文件方便地转成可读文本，并解析资源引用关系。

## 何时触发

- 用户想看某个资产 import 之后的 SerializedFile 内容
- 用户想反查 Library 里某个文件是哪个 asset 生成的
- 用户想看一个 prefab/scene/material 引用了哪些其他资源
- 用户提供 `.meta` 文件、`Library/Artifacts/...` 路径、或 Unity project 根目录

## 前置约定

### Project 路径来源

skill 不持久化 project 路径。每次调用都需要一个 Unity project 根目录（含 `Assets/` 和 `Library/`）。来源优先级：

1. 用户在当前消息中显式给出（如 "在 F:/MyGame 里看 xxx"）
2. 对话上下文中最近一次确认过的 project 路径
3. 当前 shell 工作目录（如果它本身是 Unity project）
4. 都没有 → 反问用户

### binary2text.exe 解析顺序

1. 用户显式传 `--bin2text <path>`
2. 环境变量 `UNITY_BINARY2TEXT`
3. 在 project 同盘扫描常见 Unity Hub 路径：
   - `C:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
   - `D:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
   - 同盘 `Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe`
4. fallback `f:/jnunity-2022-310/artifacts/Binary2Text/release_Win64_VS2019/binary2text.exe`
5. 找不到 → 报错并打印上述顺序，提示用户传 `--bin2text`

CLI: `binary2text inputbinaryfile [outputtextfile] [-detailed] [-largebinaryhashonly] [-hexfloat]`

skill 默认带 `-detailed`。

### 输出目录

固定 `<project>/Temp/unity-artifact-skill/`。Unity 启动会清理 Temp，符合"临时"语义。
首次使用前 `mkdir -p`。

文件命名：`<asset-basename>.<artifactID-first8>.txt`，避免同名覆盖。

## 三个动作

### 1. inspect — asset → artifact 文本

**输入：** asset 路径（`Assets/Models/Cube.fbx`）或 GUID

**步骤：**
1. 如果是 asset 路径：读 `<path>.meta`，提取 `guid: xxxxxxxx` 拿到 32 字符 GUID
2. GUID 前 2 字符 → 进入 `<project>/Library/Artifacts/<2chars>/`
3. 在该目录下用 `find ... -type f` 列出所有以 `<剩余30字符>` 开头的文件（同一个 asset 可能有多个 artifact，对应不同 importer hash）
4. 取**最新修改时间**的那个作为当前生效 artifact
5. `binary2text.exe <artifact> <Temp/unity-artifact-skill/<name>.<id8>.txt> -detailed`
6. 返回 .txt 路径 + 头 50 行预览给用户

**异常：**
- 没有 .meta → "asset 未被 Unity import，或路径错误"
- artifact 目录不存在或为空 → "asset 尚未 import / Library 已清理 / 该 asset 没有 import 产物（如 .cs 脚本）"

### 2. whose — artifact → asset

**输入：** `Library/Artifacts/<2>/<rest>` 文件路径，或任意 artifact ID 字符串

**步骤：**
1. 从输入提取 artifact ID 的前 32 字符（前 2 字符 + 文件名前 30 字符拼起来 = guid hex）
2. 实际上 artifact 文件名前 32 字符 = guid（小端 hex），后面是 importer hash
3. **默认走 .meta 索引**：
   - 检查缓存 `<project>/Temp/unity-artifact-skill/guid-index.tsv`
   - 缓存不存在或比 `Assets/` 任意 .meta 旧 → 重建：`find Assets/ -name '*.meta'` 逐个 grep `^guid: ` 写入 `<guid>\t<asset-path>` 格式
   - 在缓存中查 guid → asset 路径
4. **可选 `--use-lmdb`**（检测到 `mdb_dump` 可用时）：
   - 直接 `mdb_dump Library/SourceAssetDB` 并解析 key/value（schema 见 `references/lmdb-schema.md`）
   - 第一版**不实现**，留 stub 抛 NotImplemented

**输出：** asset 路径 + guid + 所有同 guid 的 artifact 列表（带修改时间）

### 3. refs — asset → 引用的其他资源列表

**输入：** asset 路径 或 GUID

**步骤：**
1. 复用 inspect 拿到 .txt
2. `grep -oE 'guid: [0-9a-f]{32}' <txt> | sort -u` 提取所有引用 GUID
3. 去掉 asset 自身的 guid
4. 每个 guid 用 whose 的索引反查 asset 路径
5. 未找到的 guid 标为 `<builtin or internal>`（Unity 内置资源 GUID 通常以 `0000000` 开头）

**输出格式：**
```
<asset-path> 引用了 N 个外部资源：
  abc123...  →  Assets/Materials/Red.mat
  def456...  →  Assets/Textures/wood.png
  0000000f...  →  <builtin: Default-Material>
  ...
```

## 实现要点

### .meta scan 性能

中等项目（5k-20k assets）：纯 grep 几秒内完成。命令：

```bash
find <project>/Assets -name '*.meta' -type f -print0 | \
  xargs -0 grep -lH '^guid: ' | \
  while read f; do
    g=$(grep -m1 '^guid: ' "$f" | awk '{print $2}')
    a="${f%.meta}"
    a="${a#<project>/}"
    printf '%s\t%s\n' "$g" "$a"
  done > guid-index.tsv
```

Windows / Git Bash 下注意路径分隔符（forward slash 全程使用）。

### Artifact ID 与 GUID 的关系

经 ArtifactDB.cpp 与 SourceAssetDB.cpp 验证：
- `Library/Artifacts/<2>/<30+hash>` 中前 32 字符（含目录名）= 该 asset 的 GUID（hex 小端）
- 剩余字符是 importer hash，区分同一 asset 在不同 importer settings/version 下的多份产物
- 当前生效的 artifact 在 ArtifactDB 里有 "current" 标记，但**简化策略**是取目录下最新 mtime 的文件，实际效果一致（Unity import 完成后会更新 mtime）

### 不做的事

- 不解析 LMDB 二进制 schema（第一版）
- 不做反向 "谁引用了这个 GUID"（需要全 Library 扫描+索引，第一版 scope 之外）
- 不修改 Library 任何文件，纯只读

## 错误与降级

| 情况 | 行为 |
|---|---|
| project 路径无 `Library/` | "该路径未被 Unity 打开过，无 import 产物" |
| Unity Editor 正在运行该 project | .meta scan 不受影响；将来 LMDB 模式会失败，提示用户关闭 Editor |
| binary2text 找不到 | 打印解析顺序，让用户传 `--bin2text` |
| asset 是脚本 (.cs) / shader 源码 | "该资产无二进制 import 产物" |
| artifact 文件 < 16 字节 | "artifact 损坏或空文件" |

## 参考

- `references/library-layout.md` — Unity 2022 `Library/Artifacts/` 结构详解
- `references/binary2text-output.md` — binary2text 输出格式样例与 guid 引用提取的正则依据
- `references/lmdb-schema.md` — SourceAssetDB / ArtifactDB 的 LMDB key/value 布局（后续扩展锚点）
