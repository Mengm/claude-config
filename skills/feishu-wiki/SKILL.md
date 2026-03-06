---
name: feishu-wiki
description: 飞书知识库/Wiki 操作。当用户涉及以下场景时触发：(1) 查看知识库列表（"有哪些知识库"、"知识空间列表"）(2) 浏览知识库内容（"看一下XX知识库"、"Wiki里有什么"）(3) 创建知识空间（"建个知识库"、"新建Wiki"）(4) 创建Wiki页面（"往知识库加一篇"）(5) 获取Wiki页面信息 (6) 整理/归类知识库文章（"整理wiki"、"按主题分类"、"检查孤儿文章"、"目录整理"）。当用户提到知识库、Wiki、知识空间时也应触发。
---

# 飞书知识库 / Wiki

通过飞书开放平台 Wiki V2 API 浏览和管理知识库内容。

## 前置条件

- Wiki 所有操作使用 `user_access_token`（显式传 `as_user=True`），因为 tenant token 看不到用户加入的知识空间
- `feishu_auth.py` 默认 tenant token，不做自动 fallback，调用方显式选择
- 首次使用前需运行 `uv run python feishu_oauth.py authorize` 完成 OAuth 授权

## 脚本路径

所有脚本位于 `.claude/skills/feishu-wiki/scripts/`，使用共享鉴权模块 `feishu_auth.py`。

## 操作

### 创建知识空间（需要 user_access_token）

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action create-space --title "知识空间名称"
```

可选 `--description` 添加描述。

### 列出知识空间

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action list-spaces
```

精简输出（只返回 space_id/name，省 context）：
```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action list-spaces --brief
```

可选：`--page-size`（默认 20）、`--page-token`

### 获取知识空间详情

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action get-space --space-id "7xxxxx"
```

### 列出知识空间节点（子页面）

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action list-nodes --space-id "7xxxxx"
```

精简输出（只返回 node_token/title/obj_type，省 context）：
```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action list-nodes --space-id "7xxxxx" --brief
```

可选参数：
```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action list-nodes --space-id "7xxxxx" \
  --parent-node-token "wikcnxxxx" \
  --page-size 50
```

- `--parent-node-token`：父节点 token，不传则列出顶层节点
- 查询「我的文档库」时 `--space-id` 可用 `my_library`

### 获取节点信息

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action get-node --token "wikcnxxxx"
```

可选 `--obj-type`：`doc` / `docx` / `sheet` / `mindnote` / `bitable`

### 创建节点（Wiki 页面）

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action create-node --space-id "7xxxxx" \
  --title "新页面标题" \
  --obj-type docx
```

可选 `--parent-node-token` 指定父节点。

### 移动已有文档到知识空间

将 Drive 中已有的文档移入 Wiki 空间（需要 user_access_token）：

```bash
uv run python .claude/skills/feishu-wiki/scripts/wiki_crud.py \
  --action move-to-wiki --space-id "7xxxxx" \
  --token "document_id_or_obj_token"
```

可选参数：
- `--obj-type`：文档类型（默认 `docx`，支持 `sheet` / `bitable` / `mindnote`）
- `--parent-node-token`：目标父节点

## 节点类型说明

- `origin` — 在知识库中创建的原生节点
- `shortcut` — 快捷方式（引用其他节点）

## 必须输出链接

**创建或修改 Wiki 页面后，必须将链接发给用户。** 格式：`https://{FEISHU_DOMAIN}/wiki/{node_token}`。`FEISHU_DOMAIN` 从环境变量获取（默认 `feishu.cn`）。

## 整理知识库目录

当用户要求整理/归类 Wiki 文章时，按以下流程操作：

1. **遍历全量结构**：用 `list-nodes --brief` 递归遍历所有层级，拿到完整树形结构
2. **识别问题**：找出孤儿文章（顶层散落）、分类错位（文章主题与所在目录不匹配）、目录过大需拆子目录
3. **提出方案**：向用户展示当前结构 + 调整建议，等待确认后再执行
4. **执行调整**：
   - 新建子目录：`create-node --parent-node-token <父目录>`
   - 移动文章：`move-node --token <文章> --target-parent-token <目标目录>`
   - 跨目录移动同理，move-node 支持任意父节点
5. **验证结果**：移动完成后重新遍历，确认无遗漏

**原则**：
- 优先用子目录而非拆分顶层目录（保持顶层 5-8 个，认知负担低）
- 每篇文章必须在至少一个目录下，不允许孤儿
- 移动是安全操作（文章内容和链接不变），但删除不可逆，需用户确认

## 注意事项

- Wiki 全部操作显式使用 `as_user=True`（user token），不依赖 tenant token
- 创建节点（create-node）额外兜底：user token 失败时重试 tenant token
- **create-node 权限工作流**：创建 Wiki 节点后，tenant token 默认无写权限（错误 `1770032 forBidden`）。脚本已自动执行 `tenant_editable` 权限授予，创建成功后可直接用 tenant token 写入内容（如 `feishu-doc` 的 block 操作）
- 列出节点不递归，每次只返回直接子节点
- 获取节点内容需要配合 feishu-doc 技能读取实际文档内容（通过 obj_token）

## Failure Handling

依赖链：`wiki_crud.py`（Wiki API）→ `feishu-doc`（内容写入）

- **user_access_token 失效** → create-node 已有兜底（自动重试 tenant token）。其他操作（list-spaces 等）提示用户重新授权：`uv run python feishu_oauth.py authorize`
- **create-node 成功但后续 feishu-doc 写入失败**（权限 1770032）→ 节点已创建，展示 Wiki 链接给用户，告知"页面已创建但内容写入失败，可手动编辑或稍后重试"
- **move-to-wiki / move-node 失败** → 文档未丢失（仍在原位置），告知用户移动失败原因，不要重试可能导致重复
- **list-nodes 返回空** → 可能是权限问题（知识空间未对应用开放），提示用户检查知识空间权限设置
