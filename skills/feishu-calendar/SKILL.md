---
name: feishu-calendar
description: 飞书日历/日程操作。当用户涉及以下场景时触发：(1) 创建日程（"帮我约个会"、"明天下午3点开会"、"建个日程"）(2) 查看日程（"查一下日程"、"这周有什么安排"）(3) 删除日程（"取消那个会"）(4) 纯提醒/备忘需求（"提醒我…"、"别忘了…"、到期/续费提醒）→ 创建飞书日程。当用户提到日历、日程、会议安排、提醒时触发。
depends-on:
  - CLAUDE.md#提醒vs执行路由
  - CLAUDE.md#TASKPOOL环境变量
  - schedule  # 互斥路由：提醒→feishu-calendar，执行→schedule
---

# 飞书日历操作

通过飞书开放平台 Calendar V4 API 创建和管理日程。

## 前置条件

- 应用需开启权限：`calendar:calendar`（日历读写）
- 应用需开启 Bot 能力

## 操作指南

读取 `references/operations.md`

## 注意事项

- 脚本自动将 `$TASKPOOL_USER_ID` 加为参与人，无需手动传 `--attendees`
- 不要用 `--as-user`，直接用 Bot 身份
- `--attendees` 传入后自动串联 create + add-attendees 两步
- `--calendar-id` 不传则自动获取主日历
- 删除日程不可恢复
