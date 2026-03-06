# 日历操作详细用法

所有脚本位于 `.claude/skills/feishu-calendar/scripts/`，使用共享鉴权模块 `feishu_auth.py`。

## 创建日程

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action create \
  --summary "会议标题" \
  --start "2026-02-15T14:00"
```

可选参数：
```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action create \
  --summary "会议标题" \
  --start "2026-02-15T14:00" \
  --end "2026-02-15T15:00" \
  --description "会议议程" \
  --location "会议室A" \
  --attendees "ou_xxx,ou_yyy" \
  --reminder 15 \
  --recurrence "FREQ=WEEKLY;BYDAY=WE"
```

- 不传 `--end` 默认为 start + 1 小时
- `--all-day` 标记为全天日程
- `--reminder N` 提前 N 分钟提醒
- `--attendees` 逗号分隔的 open_id 列表，创建后自动调用添加参与人 API
- `--no-notify` 不通知参与人
- `--recurrence` RFC 5545 RRULE 循环规则。常用示例：
  - `FREQ=DAILY;INTERVAL=1` — 每天
  - `FREQ=WEEKLY;BYDAY=MO,WE,FR` — 每周一三五
  - `FREQ=WEEKLY;BYDAY=WE` — 每周三
  - `FREQ=MONTHLY;BYMONTHDAY=1` — 每月1号
  - `FREQ=WEEKLY;BYDAY=MO;COUNT=10` — 每周一，共10次

## 删除日程

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action delete \
  --event-id <event_id>
```

## 列出日程

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action list-events \
  --start-time "2026-02-15" \
  --end-time "2026-02-16"
```

精简输出（只返回 event_id/summary/time/status，省 context）：
```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action list-events \
  --start-time "2026-02-15" \
  --end-time "2026-02-16" \
  --brief
```

## 添加参与人

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action add-attendees \
  --event-id <event_id> \
  --attendees "ou_xxx,ou_yyy"
```

## 查看可用日历

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action list-calendars
```

## 获取主日历 ID

```bash
uv run python .claude/skills/feishu-calendar/scripts/calendar_crud.py \
  --action get-primary
```

## 日程创建质量标准

创建日程时必须遵循以下规则：

- **必须给具体时间段**，不要用全天日程（`--all-day`）——全天日程容易被忽略，且在日历顶部显示不醒目。例如提醒类日程用 `10:00-10:30`。
- **description 必须包含相关链接**（管理后台、操作入口、参考资料等），方便用户在日程里一键跳转。
- **到期/续费提醒类日程**：安排在到期前最近的周末或前一个工作日，不要提前太久。
- **时区意识**：用户在东八区（Asia/Shanghai）。传 `--start "2026-04-11T10:00"` 时脚本会自动用 `SCHEDULER_TIMEZONE` 环境变量处理。
- **标题包含关键信息**：如有到期日/截止日，在标题中注明，例如「memtrix.dev 域名续费提醒（4/14到期）」。
- **面试日程默认 1 小时**（如 14:00-15:00），除非用户给了精确时间段。面试链接/HR 信息放 description。
