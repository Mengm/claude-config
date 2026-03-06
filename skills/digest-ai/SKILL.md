---
name: digest-ai
description: AI 行业日报。搜集大模型进展、爆火产品、GitHub Trending，多时间窗口交叉研判，过滤噪音发现机会和趋势。当用户要求 AI 日报、行业动态、趋势扫描，或由 scheduler 定时触发时使用。
---

# AI 日报

存档目录：`$TASKPOOL_USER_DESK/digest-ai/`

## 路由

- **数据源配置**（各源的 URL、API、抓取方式、筛选标准）→ 读取 `references/sources.md`
- **输出格式**（大佬动态、正文条目、链接格式、实体背景、信源发现）→ 读取 `references/output-format.md`

## 并行拆解

用 Task 工具并行拉取各数据源，每个 subagent 独立完成抓取和初筛：

```
Task 1 (subagent): X/Twitter 大佬 + HN + HF Papers
Task 2 (subagent): Product Hunt + GitHub Trending + 少数派 + Lex Fridman + Dwarkesh + Agent Memory 研究追踪
Task 3 (subagent): WebSearch 补充（1天/3天/7天三窗口）
Task 4 (subagent): 92 个顶级博客 RSS 源（读取 references/top-blog-rss.md）
主 agent: 汇总去重 → 交叉研判 → 生成最终日报
```

每个 Task 使用 `subagent_type: "general-purpose"`。四个 Task 必须**并行发起**。

**重要**：subagent 只负责返回抓取数据，**不要**在 subagent 的 prompt 中提及 `[OUTPUT_FILE]` 标签。`[OUTPUT_FILE]` 只由主 agent 在最终保存日报后输出一次。

## 检索策略

Task 3 的 WebSearch 分三个时间窗口：
- **1 天**：昨天的新事件
- **3 天**：持续发酵、热度上升的话题
- **7 天**：形成趋势的方向

多个窗口反复出现 = 真趋势，单窗口 = 可能是噪音。

## 信息稀疏降级

Task 1 + Task 2 完成后检查信息量：如果 HN 过去 24 小时 points>50 的 AI 帖少于 3 条，**且** GitHub Trending 无 AI 项目进前 10，判定为信息稀疏日。此时不必等 Task 3，直接基于已有数据汇总。

## 关注维度

0. **AI 领袖动态** — 核心人物一手发声，与其他信源交叉印证时置信度最高
1. **大模型重大进展** — 新模型发布、能力突破、重要论文
2. **爆火产品/工具** — 突然走红或增长显著的 AI 产品
3. **GitHub Trending AI 项目** — star 增长异常快的
4. **社区热议话题** — HN 高评论帖
5. **深度观点与行业内幕** — 深度播客中的战略判断、技术路线

## 去重

1. 读取 `$TASKPOOL_USER_DESK/digest-ai/` 下最近 7 天存档，跳过已报道内容（除非有重大更新）
2. 每条标注「新发现」或「持续跟踪」

## 存档清理

生成日报后，删除 `$TASKPOOL_USER_DESK/digest-ai/` 下超过 7 天的 .md 文件，只保留最近 7 天。

## Anthropic 工程博客联动

日报中发现 Anthropic 工程博客新文章时，额外执行：
1. WebFetch 爬取全文
2. 确认 `kb/anthropic-engineering.md` 未收录
3. 按现有分类追加要点
4. git commit + push

## Agent Memory 研究联动

日报中发现 RLM / Letta / Prime Intellect / agent memory 相关新进展时，额外执行：
1. 确认 `kb/agent-memory-research.md` 未收录
2. 追加论文/项目/重要更新
3. 如为 Letta 博客新文章，同步更新 `kb/letta-engineering.md`
4. git commit + push

## Failure Handling

依赖链：4 个并行 subagent → 汇总去重 → KB 联动（可选）

- **单个 subagent 超时/失败** → 不阻塞汇总。用已返回的 subagent 数据继续，在日报开头注明"以下数据源暂不可用：[失败源名称]"。至少 2 个 subagent 成功即可出日报
- **所有 subagent 失败**（网络全挂）→ 告知用户"数据源全部不可用，建议稍后重试"，不要生成空日报
- **WebSearch 不可用** → 跳过 Task 3 的多窗口检索，基于 Task 1 + Task 2 数据汇总，日报标注"缺少 WebSearch 交叉验证"
- **KB 联动失败**（git commit/push 失败、kb 文件写入失败）→ 不影响日报本身，告知用户"KB 更新失败，日报已正常生成"
- **存档目录不存在** → 自动创建 `$TASKPOOL_USER_DESK/digest-ai/`，不要报错
- **去重读取旧存档失败** → 跳过去重，全量输出，标注"未去重（历史存档读取失败）"
