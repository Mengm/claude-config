---
name: kb-distill
description: 知识蒸馏：将 kb/ 散乱事实提炼为 AI 决策规则，建立交叉索引，执行知识代谢（升级到 CLAUDE.md / 降级归档 / 淘汰）。触发场景：(1) 用户说"整理 kb"、"提炼规则"、"蒸馏"、"distill" (2) kb 文件超过 500 行需要瘦身 (3) 用户要求从文档/URL 提取 AI 可执行规则 (4) 定期知识代谢（scheduler 触发） (5) 用户说"这条规则该进 CLAUDE.md" 或"这段已经过时了"
depends-on:
  - CLAUDE.md#KB Just-in-Time Retrieval
---

# KB Distill — 知识蒸馏与代谢

将散落在 kb/ 中的 L1 事实（发生了什么 → 怎么修）提炼为 L2 决策规则（When X → Do Y → Because Z），建立交叉索引，执行知识在层级间的升降级。

## 核心原则

**kb/ 是给 AI 看的认知补丁。** 每条内容的存在理由是：没有它，AI 会在某个场景犯某个具体错误。蒸馏的目标不是"整理得好看"，而是"让 AI 下次不犯同样的错"。

## 路由

- **从 kb 文件提炼规则** → 读取 `references/decision-rules.md`
- **知识代谢**（升级/降级/归档/淘汰）→ 读取 `references/metabolism.md`
- **外部文档消化**（URL/文件 → AI 规则提取）→ 读取 `references/decision-rules.md` + 用 `web-read` 或 `feishu-doc` 获取内容
- **交叉索引**（建立 kb 文件间的 See Also 关系）→ 直接执行下方流程

## 输入类型

1. **kb 文件名** — `distill field-notes.md` → 扫描该文件提取规则
2. **kb 全局 / 代谢** — `distill all` / `代谢` / `metabolism` → 全量扫描，生成交叉索引 + 代谢建议
3. **URL/文档** — `distill <url>` → 获取内容，提取 AI 可执行规则写入 kb/

## 蒸馏流程

### Step 1: 扫描与分类

读取目标 kb 文件，将每个条目标记层级：
- **L1 事实**：记录了"发生了什么"和"怎么修的"，缺少泛化规则
- **L2 决策规则**：已有 When → Do → Because 结构，可直接被 AI 复用
- **L3 原则**：跨场景的架构原则/心智模型

### Step 2: L1 → L2 提炼

对每个 L1 条目，提取决策规则。详细格式 → `references/decision-rules.md`

### Step 3: 交叉索引

扫描提炼后的规则，找出跨文件关联：
- 同一概念在多个文件出现 → 添加 `→ See also: file.md#section`
- 一个规则的前置条件在另一个文件解释 → 添加引用
- 输出格式：在条目末尾追加 `→ See also:` 行

### Step 4: 代谢建议

根据 `references/metabolism.md` 的标准，输出代谢建议清单。不自动执行，等用户确认。

## 外部文档消化

将 URL/文档转化为 AI 可执行规则，**不**原文存储。流程：
1. 获取内容（web-read / feishu-doc / 直接读文件）
2. 提取与 DutyAI 相关的可执行洞察（忽略纯背景叙述）
3. 格式化为决策规则，写入 kb/ 中对应主题的文件
4. 在来源行标注 `(source: <url>, distilled <date>)`

## 输出质量 gate

- 每条规则必须能回答"AI 不知道这条会在哪犯错？" → 说不出就删
- 决策规则必须有 When/Do/Because 三要素
- 交叉索引必须双向（A 引用 B，B 也引用 A）
- 代谢建议必须附具体依据（引用次数、最后使用日期、被 CLAUDE.md 覆盖）

## 与 kb-forge 协作

- **forge → distill**：forge 产出的人类分析文档，distill 从中提取 AI 规则写入 kb/
- **distill → forge**：distill 发现的跨文件模式，可作为 forge 的选题素材
- 协作方式：用户显式指定，不自动触发对方
