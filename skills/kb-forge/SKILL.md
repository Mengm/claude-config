---
name: kb-forge
description: 知识锻造：将原始素材锻造为有观点、有决策树、有时效判断的深度分析文档，改变读者心智模型。触发场景：(1) 用户说"写一篇分析"、"深度思考"、"forge"、"锻造" (2) 用户给出主题/URL 要求产出有观点的文档而非摘要 (3) 用户说"帮我想清楚这个问题" (4) 讨论到了需要跨领域综合的复杂话题 (5) 用户要求从 kb/ 素材产出对外输出（博客、备忘录、决策文档）
depends-on:
  - CLAUDE.md#KB Just-in-Time Retrieval
  - CLAUDE.md#Communication Style
---

# KB Forge — 知识锻造

将原始素材（kb/ 条目、URL、对话、零散想法）锻造为有思想的分析文档。不是总结，是锻造——产出物应该改变读者对问题的理解方式。

**"有思想" = 读完后读者知道在不同条件下该做什么选择，而不只是知道了更多信息。**

## 核心原则

摘要 aggregates information。锻造 forges judgment。差异在于：
- 摘要："X 有 A、B、C 三个特点"
- 锻造："如果你的约束是 P，选 A；如果是 Q，选 B；C 看起来有用但在 R 条件下会反噬，因为..."

## 路由

- **质量标准**（"有思想"文档的检查清单）→ 读取 `references/quality-standards.md`
- **结构范式**（文档骨架选择 + 各节写法）→ 读取 `references/structure-patterns.md`

## 输入类型

1. **主题** — `forge: 为什么 DutyAI 用 SQLite 而不是 Redis 做任务队列` → 从 kb/ 收集素材 + 补充分析
2. **kb 文件** — `forge anthropic-engineering.md` → 将书摘升级为 DutyAI 实践指南
3. **URL/文档** — `forge <url>` → 获取内容，锻造为有观点的分析
4. **对话主题** — 当前对话涉及复杂决策 → 将讨论锻造为决策文档
5. **多素材** — `forge: <主题> using <file1> + <file2> + <url>` → 交叉综合

## 锻造流程

### Step 1: 素材收集

```bash
# 搜索 kb/ 中与主题相关的内容
grep -rl "<关键词>" $HOME/dutyai/kb/
# 搜索 field-notes 中的相关经验
grep -n "<关键词>" $HOME/dutyai/kb/field-notes.md
# 如有 URL 输入，获取外部内容
```

读取 `references/quality-standards.md`。

### Step 2: 立论

在写任何内容之前，先用一句话写下 thesis：
> "本文的核心主张是：______。读者读完后应该能够______。"

如果写不出 thesis → 素材不够或主题太散 → 告知用户，建议收窄范围。

### Step 3: 选择结构

读取 `references/structure-patterns.md`，根据主题性质选择骨架。

### Step 4: 锻造

按选定骨架展开写作。每一节都要通过 `references/quality-standards.md` 的检查。

### Step 5: 时效标注

文末必须包含：
```
**时效判断**：本文核心论点基于 <前提条件>。
当 <变化信号> 出现时，<具体哪些结论> 需要重新评估。
```

## 输出格式

- 默认输出为 markdown，写入 `$TASKPOOL_USER_DESK/forge/` 目录（首次使用 `mkdir -p` 创建）
- 用户要求 docx/pdf 时调用对应 skill 转换
- 文件名：`<主题简称>-<date>.md`
- 附 `[OUTPUT_FILE: /path/to/file]` 标签

## 输出质量 gate

在交付前对照检查（任一不通过则返工）：

1. **有论点吗？** — 第一段能否用一句话概括核心主张？
2. **有决策树吗？** — 读者能否根据自己的条件选择路径？
3. **有数字吗？** — 关键论据有具体数据支撑？
4. **有反论吗？** — 显式列出了风险和反对意见？
5. **有行动吗？** — 末尾是 action items 而非 summary？
6. **有时效吗？** — 标注了前提条件和失效信号？

## 与 kb-distill 协作

- **forge → distill**：forge 产出文档后，用户可调 distill 从中提取 AI 决策规则回写 kb/
- **distill → forge**：distill 发现跨文件模式/L3 原则时，可作为 forge 选题
- 协作方式：用户显式触发，不自动连锁
