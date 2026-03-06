# 文档写入详细用法

## 写入文档内容

通过 stdin 传入 JSON 数组，一次写入所有内容：

```bash
echo '[
  {"type": "heading2", "text": "一、章节标题"},
  {"type": "text", "text": "段落正文内容"},
  {"type": "bullet", "texts": ["要点一", "要点二", "要点三"]},
  {"type": "heading3", "text": "子章节"},
  {"type": "ordered", "texts": ["第一步", "第二步"]},
  {"type": "code", "text": "print(1)", "lang": "python"},
  {"type": "divider"}
]' | uv run python .claude/skills/feishu-doc/scripts/doc_write.py --id <document_id>
```

返回：`{"ok": true, "blocks_created": 9, "blocks_deleted": 0}`

### 替换已有文档内容

加 `--replace` 参数会先清空文档所有内容，再写入新内容（文档标题不受影响，飞书自带版本历史可随时恢复）：

```bash
echo '[
  {"type": "heading2", "text": "全新的标题"},
  {"type": "text", "text": "完全替换后的内容"}
]' | uv run python .claude/skills/feishu-doc/scripts/doc_write.py --id <document_id> --replace
```

**何时用 `--replace`**：更新已有文档的全部内容时（如定期报告、周报模板）。
**何时不用**：向文档末尾追加新内容时（默认行为）。

## Markdown 模式（推荐）

加 `--markdown` 直接传 markdown 文本，省去构造 JSON：

```bash
echo '## 章节标题
段落正文内容
- 要点一
- 要点二
- 要点三

### 子章节
1. 第一步
2. 第二步

```python
print(1)
```

---
普通段落' | uv run python .claude/skills/feishu-doc/scripts/doc_write.py --id <document_id> --markdown
```

支持完整 GFM（GitHub Flavored Markdown）语法：

**Block 级别：**
- `# ~ ######` 标题（对应飞书 heading1-6）
- `- / *` 无序列表、`1.` 有序列表
- `- [ ]` / `- [x]` 任务列表（对应飞书 todo block，保留 done 状态）
- ```` ``` ```` 代码块（带语言标记，75+ 语言高亮）
- `---` / `***` 分割线
- `![alt](path)` 图片（自动 3 步上传）
- `> 引用文本` 引用块（对应飞书 quote_container）
- GFM 管道表格（`| col1 | col2 |`，对应飞书 table block，header 行自动加粗）

**Inline 级别（所有文本块内均支持）：**
- `**加粗**` → bold
- `*斜体*` → italic
- `~~删除线~~` → strikethrough
- `` `行内代码` `` → inline_code
- `[链接文本](url)` → 可点击链接
- 以上可任意嵌套，如 `***粗斜体***`、`**粗体中有 `代码`**`

可与 `--replace` 组合使用。

**优先用 markdown 模式** — 减少 context 消耗（不需要构造 JSON 数组），只有需要精细控制 block 类型时才用 JSON。

### 容器 Block 注意事项

表格和引用块需要多步 API 创建，写入速度较慢：
- **表格**：每个 cell 一次 API 调用，5x4 表格约需 22 次调用（~8s）。超过 20 行 × 10 列自动截断。
- **引用块**：创建 quote_container 后逐一添加子块。

## Block 类型（JSON 模式）

- `text` — 段落，`"text": "string"`
- `heading1` ~ `heading9` — 标题，`"text": "string"`
- `bullet` / `ordered` — 列表，`"texts": ["a", "b"]`（每项展开为独立 block）
- `code` — 代码块，`"text": "string"`, `"lang": "python"`（可选）
- `image` — 图片，`"path": "$TASKPOOL_USER_DESK/photo.png"`（自动 3 步上传，按 JSON 顺序插入）
- `divider` — 分割线，无需 text

超过 50 blocks 自动分片，间隔 0.35s 避免 QPS 限制。

## Wiki 文档写入权限

Wiki 节点通过 user token 创建后，bot 的 tenant token 默认无编辑权限（报 `1770032 forBidden`）。需要先用 user token 设置文档的链接分享权限为 `tenant_editable`，写入完成后恢复为 `tenant_readable`：

```python
from feishu_auth import api_patch
# 写入前：开放 tenant 编辑权限
api_patch(f"/drive/v1/permissions/{obj_token}/public",
          body={"link_share_entity": "tenant_editable"},
          params={"type": "docx"})

# ... 用 tenant token 写入内容 ...

# 写入后：恢复为只读
api_patch(f"/drive/v1/permissions/{obj_token}/public",
          body={"link_share_entity": "tenant_readable"},
          params={"type": "docx"})
```

或用 `doc_share.py`：
```bash
uv run python .claude/skills/feishu-doc/scripts/doc_share.py --id <obj_token> --type tenant_edit
# ... 写入 ...
uv run python .claude/skills/feishu-doc/scripts/doc_share.py --id <obj_token> --type tenant_read
```

## Image Block API 要点

飞书文档插入图片必须走 **3 步流程**（一步创建会导致图片转圈不显示）：

1. **创建空 image block**：`POST /docx/v1/documents/{doc_id}/blocks/{doc_id}/children` body=`{"children": [{"block_type": 27, "image": {}}]}` → 返回 `block_id`
2. **上传图片**：`POST /drive/v1/medias/upload_all` (multipart) `parent_type=docx_image`, `parent_node=block_id`（不是 doc_id） → 返回 `file_token`
3. **绑定图片**：`PATCH /docx/v1/documents/{doc_id}/blocks/{block_id}` body=`{"replace_image": {"token": file_token, "width": 1024, "height": 572}}`（width/height 必须传，否则飞书默认 100x100 显示极小）

`doc_write.py` 已封装此流程，传 `{"type": "image", "path": "$TASKPOOL_USER_DESK/xxx.png"}` 即可自动处理（自动读取图片实际尺寸）。图片按 JSON 数组中的位置顺序插入文档，不会被推到末尾。
