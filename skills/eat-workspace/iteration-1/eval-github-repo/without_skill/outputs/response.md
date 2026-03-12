# Analysis: claude-code (https://github.com/anthropics/claude-code)

## Step 2: Deep Analysis

`claude-code` 是 Anthropic 官方的 Claude CLI 工具 -- 也就是你现在正在用的这个东西。作为一个"分析自己"的场景，我来梳理它真正值得关注的设计和实践。

**Core value**: Claude Code 是一个 agentic coding CLI，核心设计理念是让 LLM 直接操作本地开发环境（文件系统、终端、Git），而非停留在对话层面。它的价值不在于代码本身（TypeScript CLI），而在于它展示的 **Agent 工程模式**。

**Knowledge type**: Pattern + Workflow

**Applicability**: 每次使用 Claude Code 和设计 Agent 工作流时 -- Frequency: daily

**Shelf-life**: Long-lived（Agent 设计模式会持续演进但核心理念稳定）

**Actionability**: Heuristic + Reference

### 值得关注的设计模式

1. **CLAUDE.md 分层配置体系**
   - `~/.claude/CLAUDE.md` (全局个人) > 项目根目录 `CLAUDE.md` > 子目录 `CLAUDE.md`
   - 你已经在用这套体系了，这不是新知识。

2. **Memory 持久化机制**
   - `/memory` 命令将对话中的关键信息写入 memory 文件
   - 你已经在用 `MEMORY.md`，这也不是新知识。

3. **Hooks 系统**
   - Pre/post hook 可以在工具调用前后执行自定义脚本
   - 例如：每次 `Write` 工具写完文件后自动执行 lint，或在 `Bash` 执行前做安全检查
   - 这个你目前 **没有在用**，但潜力很大。

4. **Custom Slash Commands**
   - `.claude/commands/` 目录下放 `.md` 文件，自动变成 `/command-name`
   - 可以包含 `$ARGUMENTS` 占位符
   - 这个等价于你的 Skills 系统的轻量版本。你的 `/eat` Skill 已经比这个更强大。

5. **MCP (Model Context Protocol) 集成**
   - 通过 `.claude/settings.json` 配置 MCP server
   - 你已经在用（lark-mcp, unity-mcp），这不是新知识。

6. **Permission Model**
   - `settings.json` 中的 `allowedTools` / `deniedTools` 控制工具权限
   - 三级设置：global > project > local（`.claude/settings.local.json`）
   - 这个是运维层面的，你已经有 `settings.local.json` 在用了。

7. **多实例管理 (Worktree)**
   - 支持 git worktree 实现并行任务
   - 对你的 Unity 包单仓来说实用性有限。

8. **GitHub Integration Patterns**
   - `claude -p "..." --allowedTools ...` headless 模式用于 CI/CD
   - 可以作为 GitHub Actions 的一环，自动 code review 或 PR 生成
   - 你的项目是内部 Git 仓库，直接适用性不高。

## Step 3: Impact Scan

```
Impact Scan Results:
- Conflicts: None
- Overlaps:
  - /eat Skill 已覆盖 "custom commands" 的理念 (~70%)
  - CLAUDE.md 分层配置你已经在实践 (~100%)
  - MCP 配置你已经在用 (~100%)
  - Memory 机制你已经在用 (~100%)
- Gaps:
  - Hooks 系统的具体使用模式（你还没有 hooks 配置）
- Stale: None
```

## Step 4: Digestion Recommendation

```
Recommendation: Path A — Don't Eat (大部分) + 关注 Hooks

Reason: claude-code 是你每天在用的工具，它的核心概念你已经全部掌握并实践：
- CLAUDE.md 分层配置 ✓
- Memory 持久化 ✓
- MCP 集成 ✓
- Custom commands → 你的 Skills 系统更强大 ✓
- Settings 分级管理 ✓

唯一的 Gap 是 Hooks 系统，但这属于 "需要实际使用场景驱动" 的功能。
当你遇到需要在工具调用前后自动执行某些操作的场景时（比如 lint、format、安全检查），
再按需配置 hooks 即可。现在为它建规则或 Skill 属于过早优化。

Expected effect: 无变更。确认你对 Claude Code 的掌握已经足够全面。
Risk: None
```

## 总结

你对 claude-code 的运用已经相当深入 -- 实际上你的 Skills 系统（`/eat`、analysis-framework）在某些方面比 claude-code 原生的 custom commands 更高级。这个仓库对你来说 **没有需要吸收的新知识**。

唯一值得留意的是 **Hooks 系统**（`~/.claude/settings.json` 中配置 `hooks`），等你有具体需求时再启用。不建议现在就创建相关 Skill 或规则。
