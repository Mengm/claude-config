# /eat: Analyzing https://github.com/anthropics/claude-code

---

## Step 1: Identify & Fetch Input

**Input type**: GitHub repository link
**Source**: `https://github.com/anthropics/claude-code` — Anthropic's official CLI tool for Claude

Since I cannot clone the repo in this context, I'm working from my knowledge of claude-code. It is Anthropic's official agentic coding CLI that lets Claude operate directly in your terminal — reading files, editing code, running commands, managing git, and interacting with your codebase. Key components include:

- **Agentic loop**: Claude autonomously plans, executes, and iterates using tools (Bash, Read, Write, Edit, Grep, Glob, etc.)
- **CLAUDE.md convention**: Project-level and user-level instruction files that customize Claude's behavior per-project
- **Permission model**: Tool-use permissions with allow/deny lists, sandboxing
- **Hooks system**: Pre/post execution hooks for tool calls (PreToolUse, PostToolUse, etc.)
- **Slash commands**: User-defined `/commands` via markdown files
- **Skills system**: Structured knowledge bundles (SKILL.md + references/ + scripts/)
- **Plugins system**: Marketplace-style plugin architecture for extending capabilities
- **MCP integration**: Model Context Protocol for connecting to external tools/services
- **Memory system**: Persistent memory across sessions via memory files
- **Multi-instance support**: Running multiple Claude Code instances
- **Git-aware**: Deep integration with git workflows (commits, PRs, branching)
- **SDK**: Agent SDK for building programmatic agents on top of Claude Code

---

## Step 2: Deep Analysis

### Analysis: claude-code (Anthropic's CLI for Claude)

**Core value**: Claude-code defines the canonical patterns for how an AI coding agent should structure its configuration, permissions, knowledge persistence, and tool orchestration. The architecture decisions (CLAUDE.md hierarchy, skills/commands/hooks/plugins separation, permission model) represent battle-tested patterns for agentic AI systems.

**Knowledge type**: Architecture pattern + Tool ecosystem knowledge

**Applicability**: Every time we configure Claude Code, build skills, write CLAUDE.md, or design agentic workflows. Frequency: **daily**.

**Shelf-life**: **Long-lived** — This is the official tool we are running inside of. Its patterns will evolve but the core architecture is stable.

**Actionability**: Mixed — some parts are **decision rules** (how to structure CLAUDE.md), some are **reference** (available hooks/events), some are **background** (how the permission system works internally).

**Key takeaway**: We are already using claude-code. The question is whether there are specific patterns or features we're not leveraging that could improve our workflow.

---

## Step 3: Impact Scan

```
Impact Scan Results:

- Conflicts: None identified. The repo IS the tool we're using, so its patterns
  are by definition compatible.

- Overlaps:
  - ~/.claude/CLAUDE.md "Knowledge Digestion Protocol" — already covers the meta-workflow
    for absorbing knowledge (~90% overlap with understanding CLAUDE.md conventions)
  - ~/.claude/skills/SKILL.md ("eat" skill) — already covers the skill system pattern
    by being an instance of it (~80% overlap)
  - ~/.claude/CLAUDE.md "Git Sync Protocol" — already covers git workflow (~70% overlap
    with claude-code's git conventions)

- Gaps (genuinely new things we might not be leveraging):
  1. **Hooks system**: No rules or skills currently reference PreToolUse/PostToolUse hooks
     for automated validation or guardrails
  2. **Slash commands**: No custom /commands found in ~/.claude/commands/
  3. **Subagent patterns**: The Agent tool / subagent delegation pattern for parallel work
  4. **SDK usage**: Building programmatic agents via the Agent SDK
  5. **Plugin development patterns**: While plugins are installed, no custom plugins exist

- Stale: Nothing — existing rules are compatible and current
```

---

## Step 4: Digestion Recommendation

```
Recommendation: Path A — Don't Eat (with caveats)

Reason: This is the tool we are literally running inside of. Claude already has deep
knowledge of claude-code's architecture, conventions, and capabilities because it IS
the runtime. Absorbing the repo would be internalizing knowledge about ourselves —
largely redundant.

The genuine gaps identified (hooks, custom commands, subagents, SDK) are real, but they
are FEATURES TO USE, not KNOWLEDGE TO INTERNALIZE. The right action is to use those
features when a concrete need arises, not to preemptively document them.

Expected effect: No changes to configuration. User is informed of underutilized features.

Risk: None — we avoid unnecessary bloat in our knowledge base.
```

### However — Actionable Insights Worth Noting

While I recommend Path A (don't eat the repo as a whole), here are the specific underutilized features you might want to explore:

| Feature | What It Does | When to Adopt |
|---------|-------------|---------------|
| **Custom /commands** (`~/.claude/commands/*.md`) | Reusable prompt templates invoked with `/command-name` | When you find yourself typing the same complex prompt repeatedly |
| **Hooks** (`~/.claude/settings.json` hooks config) | Auto-run scripts before/after tool calls | When you want automated checks (e.g., lint before commit, validate before file write) |
| **Subagents** (Agent tool) | Delegate subtasks to parallel Claude instances | When a task naturally decomposes into independent subtasks |

If any of these interest you, I can help set them up — that would be a concrete task, not a knowledge absorption task.

---

## Step 5: Execute

**Path A selected — no changes made.**

The claude-code repo is the tool we're running inside of. Its patterns are already our patterns. The key insight from this analysis is not "what to absorb" but "what features we're not yet using" — and those are better addressed by doing, not by documenting.

If you want to explore any of the underutilized features (hooks, custom commands, subagents), just say the word and we can set them up concretely.
