---
name: desk
description: 用户桌面工作空间（$TASKPOOL_USER_DESK）。管理主项目之外的文件、代码、素材。当用户给出 GitHub URL 要求拉取/分析代码、存放临时文件素材、查看或清理桌面内容、提到 desk 目录时触发。
---

# 用户桌面

工作目录：`$TASKPOOL_USER_DESK`（运行时环境变量确定，admin = `~/desk/`，其他用户 = `~/desk/<user_id>/`）

此目录不在任何 git 仓库内，是用户的持久化工作空间 — 相当于桌面、浏览记录、外部记忆。主项目代码在项目根目录，这里放的是主项目之外的一切。

## 目录里可以有什么

- 拉取的参考代码仓库
- 临时文件、素材、草稿
- 从网上保存的文档、数据
- 用户的笔记和备忘
- 任何用户想留着以后用的东西

## 操作识别

根据用户输入判断操作：

- **GitHub URL** → clone 代码仓库并分析
- **"list" / "列表" / "桌面上有什么"** → 列出桌面内容
- **"clean" / "删除" + 名字** → 删除指定内容
- **名字 + 问题** → 在已有内容中查找回答
- **存放文件/素材** → 创建子目录并归档

## Clone 代码仓库

1. 确保 `$TASKPOOL_USER_DESK` 存在
2. 从 URL 提取仓库名（如 `openclaw/openclaw` → `openclaw`）
3. 如果目录已存在，跳过 clone，直接进入分析
4. shallow clone：`git clone --depth 1 <url> $TASKPOOL_USER_DESK/<repo-name>`
5. clone 失败 → 报错并提示检查 URL 或网络

### 代码分析

clone 完成后用 Explore agent 分析，覆盖：

- 语言/框架、项目规模、目录结构
- 入口文件、核心模块、模块划分方式
- 测试框架、测试文件位置、命名约定、测试分层
- 代码风格、错误处理、依赖注入方式
- 优先读取 CLAUDE.md / AGENTS.md / CONTRIBUTING.md

如果用户明确说了想看什么（如"测试怎么组织的"），优先深挖那个方向。

## List 操作

列出 `$TASKPOOL_USER_DESK` 下所有内容，每个显示：
- 名称
- 类型（git 仓库 / 普通目录 / 文件）
- 磁盘占用（`du -sh`）
- 如果是 git 仓库，显示来源 URL（从 `.git/config` 读取）
- 如果是目录/文件，显示创建或修改时间

## Clean 操作

- 指定名字：`rm -rf $TASKPOOL_USER_DESK/<name>`，操作前确认
- clean all：`rm -rf $TASKPOOL_USER_DESK/*`，操作前确认

## 注意事项

- clone 只做 shallow（`--depth 1`），不需要完整历史
- 分析时用 Explore agent 并行，避免阻塞主对话
- 大型 monorepo 提醒用户可能很大，确认后再 clone
- 分析结果直接回复用户，不写额外文件
