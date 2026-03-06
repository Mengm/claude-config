---
name: feishu-task
description: 飞书任务管理。当用户涉及以下场景时触发：(1) 创建/完成/删除任务（"建个任务"、"加个待办"、"标记完成"）(2) 管理任务清单（"看看待办"、"任务列表"）(3) 子任务管理。当用户提到飞书任务、待办、to-do时触发。注意：日程/日历/提醒需求请使用 feishu-calendar skill。
depends-on:
  - CLAUDE.md#TASKPOOL环境变量
---

# 飞书任务管理

通过飞书开放平台 Task V2 API 创建和管理任务。

## 前置条件

- 应用需开启权限：`task:task`（任务读写）
- 应用需开启 Bot 能力

## 操作指南

读取 `references/operations.md`

## 注意事项

- 脚本自动将 `$TASKPOOL_USER_ID` 加为负责人，无需手动传 `--assignee`
- 不要用 `--as-user`，直接用 Bot 身份
- List Tasks API 只支持 user_access_token，用 `list-tasklist` 代替
- 删除任务不可恢复
