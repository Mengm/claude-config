---
name: feishu-bitable
description: 飞书多维表格（Base/Bitable）操作。当用户涉及以下场景时触发：(1) 创建/管理数据表（"建个多维表格"、"加一张表"）(2) 读写记录（"查一下表里的数据"、"往表里插入记录"、"更新记录"）(3) 管理字段/列（"加一列"、"修改字段类型"）(4) 搜索/筛选记录（"找出所有状态为完成的记录"）。当用户提供多维表格 URL 或 app_token 时也应触发。
---

# 飞书多维表格操作

通过飞书开放平台 API 操作多维表格（Bitable/Base），支持表、字段、记录的完整 CRUD。

## 前置条件

- 应用需开启 `bitable:app` 权限
- 多维表格需对应用可见（应用已被添加为协作者）

## 脚本路径

所有脚本位于 `.claude/skills/feishu-bitable/scripts/`，使用共享鉴权模块 `feishu_auth.py`。

## 从 URL 提取 token

多维表格 URL 格式：`https://xxx.feishu.cn/base/APP_TOKEN?table=TABLE_ID&view=VIEW_ID`

## 路由

所有操作（创建表/字段管理/记录CRUD/分享/字段类型编号）→ 读取 `references/operations.md`

## 注意事项

- 同一数据表不支持并发写入，会返回 1254291 写入冲突错误
- 单次批量创建上限 500 条记录
- 每个 Base 最多 100 张表 + 仪表盘
- 每张表最多 20,000 条记录
- 日期字段使用毫秒级时间戳
- 人员字段传 open_id/union_id/user_id
- 将 Bitable 数据展示为飞书卡片 table 时，每列最小宽度 80px，低于此值会触发 `200912` 错误导致整张卡片创建失败
