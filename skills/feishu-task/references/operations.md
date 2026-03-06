# 任务操作详细用法

所有脚本位于 `.claude/skills/feishu-task/scripts/`，使用共享鉴权模块 `feishu_auth.py`。

## 创建任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action create --summary "任务标题"
```

可选参数：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action create \
  --summary "任务标题" \
  --description "详细描述" \
  --due "2026-02-20" \
  --start "2026-02-15" \
  --assignee "ou_xxxx"
```

- `--due` / `--start`：ISO 格式，`2026-02-15`（全天）或 `2026-02-15T14:00`（精确时间）
- `--assignee`：额外负责人 open_id（脚本会自动将 `$TASKPOOL_USER_ID` 加为负责人，无需手动传）

## 完成任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action complete --task-id <guid>
```

## 恢复未完成

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action uncomplete --task-id <guid>
```

## 查看任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action get --task-id <guid>
```

## 删除任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action delete --task-id <guid>
```

## 添加成员

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action add-member --task-id <guid> \
  --member-ids "ou_xxx,ou_yyy" \
  --role assignee
```

`--role` 可选 `assignee`（负责人）或 `follower`（关注者）。

## 创建子任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action create-subtask \
  --parent-id <parent_guid> \
  --summary "子任务标题"
```

## 列出清单内任务

```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action list-tasklist --tasklist-id <tasklist_guid>
```

精简输出（只返回 guid/summary/completed_at，省 context）：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action list-tasklist --tasklist-id <tasklist_guid> --brief
```

## 清单管理（Tasklist）

创建清单：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action create-tasklist --name "清单名称"
```

列出所有清单：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action list-tasklists [--brief]
```

将任务加入清单：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action add-to-tasklist --task-id <guid> --tasklist-id <tasklist_guid>
```

删除清单：
```bash
uv run python .claude/skills/feishu-task/scripts/task_crud.py \
  --action delete-tasklist --tasklist-id <tasklist_guid>
```

## 任务分类规则

批量创建任务时，**必须按类别归入清单**，不要把所有任务堆在一起。推荐分类：
- **技术/Side Project** — 技术调研、产品 idea、工具试用
- **生活/健康** — 医疗、理发、日常事务
- **财务** — 银行、信用卡、账单
- **学习** — 课程、读书、技能提升
- **社交** — 约饭、婚礼、聚会

如果用户给的任务不好归类，主动创建合适的清单。一个任务可以属于多个清单。
