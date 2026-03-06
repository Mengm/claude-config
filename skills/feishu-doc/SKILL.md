---
name: feishu-doc
description: 飞书文档操作。当用户涉及以下场景时触发：(1) 读取飞书文档内容（"读一下这个文档"、"获取文档内容"）(2) 创建飞书文档（"帮我建个文档"、"写到飞书文档里"）(3) 向文档追加内容（"往文档里加一段"）(4) 分享/权限管理（"把文档分享给谁"）(5) 删除文档（"删掉这个文档"）。当用户提供飞书文档 URL 或 document_id 时也应触发。
---

# 飞书文档操作

通过飞书开放平台 API 读写飞书新版文档（docx）。

## 前置条件

- 应用需开启 `docx:document` 权限
- 文档需对应用可见（应用已被添加为文档协作者，或文档链接分享设置允许应用访问）

## 脚本路径

所有脚本位于 `.claude/skills/feishu-doc/scripts/`，使用 `feishu_auth.py` 统一鉴权。

## 路由

- **写入/编辑文档**（block 类型、图片上传、Wiki 权限）→ 读取 `references/write.md`
- **读取/创建/分享** → 见下方操作一览

## 从 URL 提取 document_id

飞书文档 URL 格式：`https://xxx.feishu.cn/docx/DOCUMENT_ID` 或 `https://xxx.feishu.cn/wiki/WIKI_TOKEN`

对于 wiki 链接，需先调用知识库 API 获取实际 document_id。

## 操作一览

### 读取文档内容

```bash
uv run python .claude/skills/feishu-doc/scripts/doc_read.py --id <document_id>
```

长文档加 `--max-chars N` 截断输出。加 `--blocks` 获取结构化 block 信息（JSON）。加 `--blocks --brief` 只输出 block_id/block_type/parent_id（省 token）。`--max-chars` 同时适用于 text 和 blocks 模式。

读取失败时 fallback 到 Jina Reader：
```bash
curl -s "https://r.jina.ai/<feishu_doc_url>" -H "Accept: text/markdown"
```

### 创建文档

```bash
uv run python .claude/skills/feishu-doc/scripts/doc_create.py \
  --title "文档标题"
```

可选：`--parent-node "wikcnxxxx"`, `--wiki-space "7xxxxx"`

创建成功后输出 document_id、URL、`granted_to`（自动授权用户）。创建后**将文档链接发给用户**。

### 分享文档

```bash
uv run python .claude/skills/feishu-doc/scripts/doc_share.py \
  --id <document_id> --type <share_type> --doc-type docx
```

权限层级：`off` → `tenant_read` → `tenant_edit` → `anyone_read` → `anyone_edit`

`--doc-type` 可选：`docx`（默认）、`bitable`、`sheet`、`file`、`wiki`

### 删除文档

```bash
uv run python .claude/skills/feishu-doc/scripts/doc_delete.py \
  --id <document_id> --type docx
```

`--type` 可选：`file`、`docx`（默认）、`bitable`、`sheet`、`mindnote`、`slides`

### 文件夹操作

```bash
# 列出云空间根目录
uv run python .claude/skills/feishu-doc/scripts/doc_folder.py --action list

# 列出指定文件夹内容
uv run python .claude/skills/feishu-doc/scripts/doc_folder.py --action list --folder-token "fldcnXXX"

# 创建文件夹
uv run python .claude/skills/feishu-doc/scripts/doc_folder.py --action create --name "文件夹名"

# 移动文件到目标文件夹
uv run python .claude/skills/feishu-doc/scripts/doc_folder.py --action move --file-token "docXXX" --target-folder "fldcnXXX"
```

## 参数速查

- `--id`: 文档 document_id（必填，除 create 外）
- `--title`: 文档标题（create 时必填）
- `--wiki-space`: Wiki 空间 ID（create 时可选，覆盖环境变量）
- `--parent-node`: Wiki 父节点 token（create 时可选）
- `--replace`: 清空已有内容后写入（write 时可选）
- `--blocks`: 获取结构化 block 数据（read 时可选）
- `--brief`: 精简 block 输出，只含 block_id/block_type/parent_id（read --blocks 时可选）
- `--max-chars N`: 截断输出到 N 字符（read 时可选，适用于 text 和 blocks，0=不限）
- `--offset N`: 从第 N 个字符开始读取（read text 模式，用于分页读取长文档）
- `--type`: 分享权限类型（share 时必填）
- `--doc-type`: 文档类型（share 时可选，默认 docx）

## 必须输出链接

**创建或修改飞书文档后，必须将文档链接发给用户。** 这是硬性要求。

- `doc_create.py` 返回 JSON 中含 `url` 字段
- 手动拼接：`https://{FEISHU_DOMAIN}/docx/{document_id}`
- Wiki 文档：`https://{FEISHU_DOMAIN}/wiki/{node_token}`

## 注意事项

- 文档 API 对 block 写入有并发限制，避免并行写入同一文档
- 大量内容建议分批写入
- 创建的文档默认放在 Wiki 知识库中（`FEISHU_WIKI_SPACE`）
- Wiki 模式创建的文档，`document_id` 是 `obj_token`，可直接传给 `doc_write.py`
