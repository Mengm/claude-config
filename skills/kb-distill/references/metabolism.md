# 知识代谢：升级 / 降级 / 归档 / 淘汰

知识在层级间流动，对应 os-memory-hierarchy.md 的分级存储管理（HSM）。

## 四种代谢操作

### 1. 升级（Promote）：kb/ → CLAUDE.md

**标准**（必须全部满足）：
- 规则在过去 2 周内被 3+ 个不同 session 触发
- 违反此规则会导致可观察的错误（不是"可能有用"）
- 规则足够简洁（1-3 行），不会让 CLAUDE.md 膨胀
- 不与已有 CLAUDE.md 规则重复或冲突

**执行方式**：
1. 在 kb/ 中标注 `[promoted → CLAUDE.md#Section, <date>]`
2. 通过 `edit-claude-md` skill 写入 CLAUDE.md（不可绕过）
3. kb/ 中保留原始条目作为详细解释（CLAUDE.md 只放精简版）

### 2. 侧移（Lateralize）：kb/ → skill references/

**标准**：
- 规则只在执行某个特定 skill 时才需要
- 放在 kb/ 导致不相关 session 也能搜到，污染检索结果

**执行方式**：
1. 移动内容到对应 skill 的 `references/` 目录
2. 在原 kb 文件中留下 `[moved → .claude/skills/<name>/references/<file>, <date>]`
3. 更新 skill 的 SKILL.md references 索引

### 3. 降级（Demote）：CLAUDE.md → kb/

**标准**（满足任一即可）：
- 规则在 CLAUDE.md 中超过 4 周，但无法举出近期被触发的场景
- 规则描述的情况已被代码/hooks 确定性保证（规则变为冗余）
- CLAUDE.md 超过 160 行需要瘦身，此规则优先级最低

**执行方式**：
1. 通过 `edit-claude-md` skill 从 CLAUDE.md 移除
2. 确认 kb/ 中已有对应内容（没有则写入）
3. 确保 CLAUDE.md 的 "KB Just-in-Time Retrieval" 检索规则覆盖此主题

### 4. 归档（Archive）：标记过时

**标准**（满足任一即可）：
- 描述的 API/工具/行为已变更，规则不再适用
- 问题已被代码修复，规则的前提条件不再成立
- 超过 8 周无任何引用或触发

**执行方式**：
1. 在条目开头标注 `[ARCHIVED <date>: <reason>]`
2. 不删除——归档条目仍可被 grep 发现，但 AI 读到 ARCHIVED 标记后知道忽略
3. 每季度可批量清理 ARCHIVED 条目

## 代谢扫描流程

执行 `distill all` 或 `代谢` 时：

### Phase 1: 数据收集

```bash
# 1. CLAUDE.md 当前行数
wc -l $HOME/dutyai/.claude/CLAUDE.md

# 2. 各 kb 文件行数
wc -l $HOME/dutyai/kb/*.md

# 3. 最近 git log 中 kb/ 文件的修改频率
git log --since="4 weeks ago" --name-only --pretty=format: -- kb/ | sort | uniq -c | sort -rn

# 4. CLAUDE.md 中引用 kb/ 的规则
grep -n "kb/" $HOME/dutyai/.claude/CLAUDE.md
```

### Phase 2: 逐文件评估

对每个 kb 文件：
1. 统计 L1/L2/L3 条目比例
2. 标记 [ARCHIVED] 候选（超过 8 周未修改 + 未被引用）
3. 标记升级候选（高频触发 + 足够简洁）
4. 标记侧移候选（只跟某个 skill 相关）

### Phase 3: 输出代谢报告

```
## 代谢报告 <date>

### 升级候选（kb → CLAUDE.md）
- [ ] <规则摘要> (from <file>#<section>) — 理由：<触发频率/影响>

### 降级候选（CLAUDE.md → kb）
- [ ] <规则摘要> (CLAUDE.md L<行号>) — 理由：<冗余/低频>

### 侧移候选（kb → skill）
- [ ] <规则摘要> (from <file>) → <target-skill> — 理由：<scope>

### 归档候选
- [ ] <条目摘要> (from <file>#<section>) — 理由：<过时/已修复>

### kb 健康指标
- CLAUDE.md: <N> 行 (<status>)
- L1:L2:L3 比例: <比例>
- 交叉索引覆盖率: <N>/<Total> 条目有 See Also
```

**不自动执行任何代谢操作。** 输出报告后等用户逐条确认。
升级操作必须通过 `edit-claude-md` skill。
