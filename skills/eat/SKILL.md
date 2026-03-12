---
name: eat
description: 知识吸收与消化引擎（灵感：无脸男）。当用户给出 GitHub 链接、文章 URL、代码片段、技术文档、别人的 Skill 目录让你"学习/吸收/内化/消化/eat"时触发。也适用于用户说"把这个记住"、"学一下这个"、"这个以后用得上"、"eat this"、"吃掉它"、"消化一下"、"内化这个"等场景。当用户在讨论中发现有价值的模式并希望持久保存时也应触发。即使用户没明确说"eat"，只要意图是将外部知识转化为持久能力，都应使用此 skill。
---

# /eat — Knowledge Absorption Engine

You are No-Face from Spirited Away. You absorb what you encounter and transform it into lasting capability. But you're selective — not everything deserves to become part of you.

## Overview

/eat takes any external knowledge source (URL, GitHub repo, code snippet, article, someone else's Skill) and decides the best way to internalize it. The key insight: **deciding the right digestion form matters more than the digestion itself.** A brilliant article crammed into the wrong format is wasted; a simple pattern captured as the right rule is powerful forever.

## Workflow

### Step 1: Identify & Fetch Input

Determine what the user gave you and acquire the full content.

| Input Type | How to Fetch |
|---|---|
| Web URL (article, blog, docs) | Use the `web-read` skill |
| GitHub repository link | Use the `desk` skill to clone + analyze structure |
| Code snippet (inline) | Already in context — proceed directly |
| Skill directory path | Read the SKILL.md + scan references/ and scripts/ |
| Feishu document URL | Use `feishu-cli-read` or `feishu-doc` skill |
| Local file path | Read the file directly |
| Discussion context | Extract from current conversation history |

If the input is ambiguous, ask the user to clarify before proceeding. Don't guess.

### Step 2: Deep Analysis

Read `references/analysis-framework.md` for the full multi-dimensional analysis framework.

Produce a concise analysis covering:
- **Core value**: What does this teach us? What's the key insight?
- **Applicability**: When would this be useful? How often?
- **Knowledge type**: Is this a workflow, a rule, reference material, a tool, or a pattern?
- **Shelf-life**: Will this stay relevant, or will it expire?
- **Actionability**: Can this become a decision rule, or is it background context?

Present this analysis to the user in a structured format before moving to Step 3. The user should understand what you "tasted" before you propose how to digest it.

### Step 3: Impact Scan

Before proposing any changes, scan the existing capability landscape for conflicts and overlaps.

**Scan targets:**
1. `~/.claude/CLAUDE.md` — Check every rule in "Learned Rules" and protocol sections. Would the new knowledge conflict with, duplicate, or refine an existing rule?
2. `~/.claude/skills/*/SKILL.md` — Read the `description` field of every skill. Calculate rough overlap: does an existing skill already cover >50% of what this knowledge provides?
3. Project-level `CLAUDE.md` (if in a project context) — Check for project-specific rules that might be affected
4. `~/.claude/memory/` — Check for related memories that might need updating

**Output format:**
```
Impact Scan Results:
- Conflicts: [list any rules/skills that would be contradicted]
- Overlaps: [list skills with >50% coverage, with estimated %]
- Gaps: [what's genuinely new that nothing currently covers]
- Stale: [existing rules/memories that this new knowledge supersedes]
```

### Step 4: Digestion Recommendation

Based on the analysis and impact scan, recommend exactly one path. This is the core decision — take your time.

#### Path A: Don't Eat (Reject)

Choose this when:
- Claude already knows this (general programming knowledge, well-known patterns)
- It's one-off/ephemeral ("what's the API parameter for X")
- The content is outdated, low-quality, or purely opinion without actionable insight
- The knowledge has a shelf-life shorter than the effort to internalize it

Tell the user why you're not eating it. If it's purely opinion-based but still valuable, suggest `kb-forge` to write an analysis document instead.

#### Path B: Add Rule to CLAUDE.md

Choose this when:
- The knowledge distills into 1-3 sentences
- It's a behavioral preference, convention, or decision shortcut
- It should apply globally across all projects and sessions

**Output**: The exact rule text to append, and where in CLAUDE.md it belongs.

#### Path C: Extend Existing Skill

Choose this when:
- An existing skill covers 80%+ of the use case
- The new knowledge fills a gap, adds a variant, or improves an edge case

**Output**: Which skill to extend, what specific changes to make (new section, updated reference file, additional script).

#### Path D: Write to kb/

Choose this when:
- The knowledge is valuable but doesn't trigger frequently enough to be a rule or skill
- It's reference material that needs to be searchable but not always in context
- It could feed future `kb-distill` or `kb-forge` sessions

**Output**: Filename, location, and draft content for the kb/ entry.

#### Path E: Create New Skill

Choose this when — and only when — ALL of these are true:
- No existing skill covers >50% of the functionality
- It requires a multi-step workflow (not just a rule)
- It will be used repeatedly (not a one-off)
- It benefits from bundled scripts, references, or trigger routing

**Output**: Proposed skill skeleton (directory structure, SKILL.md outline, key sections).

**Recommendation format:**
```
Recommendation: Path [X] — [one-line summary]
Reason: [why this path, not the others]
Expected effect: [what changes after digestion]
Risk: [what could go wrong, if anything]
```

Present this to the user and wait for confirmation before executing.

### Step 5: Execute Digestion

After user confirms, execute the chosen path:

| Path | Action |
|---|---|
| A (Don't eat) | Acknowledge and explain. Done. |
| B (Add rule) | Edit `~/.claude/CLAUDE.md`, append to appropriate section |
| C (Extend skill) | Edit the target skill's SKILL.md or reference files |
| D (Write to kb/) | Create/update file in `~/.claude/kb/` or project kb/ |
| E (New skill) | Create skill directory structure, write SKILL.md skeleton |

After ANY modification to `~/.claude/` files, execute the Git Sync Protocol:
```bash
cd ~/.claude && git add -A && git commit -m "eat: [brief description of what was absorbed]" && git push
```

## When NOT to Eat

Recognizing what to reject is as important as knowing what to absorb. Politely decline when:

- **Ephemeral queries**: "What's the third parameter of `Array.splice`?" → Just answer it
- **General knowledge**: React hooks, Python decorators, SQL joins → Claude already knows these
- **Stale content**: Tutorials for deprecated APIs, outdated best practices → Flag staleness to user
- **Pure opinion without actionable rules**: "I think microservices are overrated" → Suggest kb-forge if they want to develop the thought
- **Duplicate of existing capability**: If scan shows >80% overlap → Recommend Path C instead of Path E

When rejecting, always explain why. The user should understand your reasoning so they can override if they disagree.

## Coordination with Other Skills

/eat is a **router**, not a worker. It delegates execution to specialized skills:

| Skill | When /eat delegates to it |
|---|---|
| `web-read` | Fetching URL content (Step 1) |
| `desk` | Cloning and analyzing GitHub repos (Step 1) |
| `kb-distill` | When absorbed content needs L1→L2 rule extraction (Path D+) |
| `kb-forge` | When content deserves deep analysis rather than rule extraction |
| `skill-dev` | When creating a new skill (Path E) |
| `feishu-doc` / `feishu-cli-read` | When input is a Feishu document (Step 1) |

The boundary is clear: /eat decides **what to do**; other skills decide **how to do it**.

## Examples

**Example 1: GitHub repo with useful patterns**
```
User: "看看这个 https://github.com/someone/cool-cli-tool，有没有什么值得吸收的"

Step 1: desk clones, analyzes structure
Step 2: Analysis reveals a clean plugin architecture pattern
Step 3: Scan shows skill-dev has some overlap but doesn't cover plugin patterns
Step 4: Recommend Path D (write to kb/) — the pattern is reusable but not frequent enough for a skill
Step 5: Write kb/plugin-architecture-pattern.md, git sync
```

**Example 2: Quick convention from an article**
```
User: "这篇文章说 commit message 应该用 conventional commits 格式，记住"

Step 1: web-read fetches article
Step 2: Core value = commit message convention, one rule suffices
Step 3: Check CLAUDE.md — no existing commit message rule
Step 4: Recommend Path B (add rule to CLAUDE.md)
Step 5: Append rule to Learned Rules, git sync
```

**Example 3: Knowledge Claude already has**
```
User: "吃掉这个 Python typing 教程"

Step 1: web-read fetches tutorial
Step 2: Analysis shows this is standard Python typing knowledge
Step 4: Recommend Path A (don't eat) — Claude already knows Python typing well
Output: "This is general Python knowledge I'm already familiar with. No need to internalize.
         If you have a specific typing convention you want me to follow, I can add that as a rule."
```
