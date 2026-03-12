# /eat — Processing: "以后写 git commit message 都用 conventional commits 格式，记住这个规则"

---

## Step 1: Identify & Fetch Input

**Input type**: Discussion context (inline user instruction)
**Source**: User's direct request in conversation
**Content**: The user wants all future git commit messages to follow the [Conventional Commits](https://www.conventionalcommits.org/) format.

No fetching needed — the input is already fully specified in the conversation. Proceeding directly.

---

## Step 2: Deep Analysis

### Analysis: Conventional Commits Convention

**Core value**: Enforce a standardized commit message format (`type(scope): description`) across all projects. This improves changelog generation, semantic versioning, and commit history readability.

**Knowledge type**: Rule (behavioral convention)

**Applicability**: Every time a git commit is created — **Frequency: daily**

**Shelf-life**: Evergreen. Conventional Commits is a widely adopted, stable specification (v1.0.0). It will remain relevant indefinitely.

**Actionability**: Decision rule — "When writing a commit message, always use `type(scope): description` format"

**Key takeaway**: A single, clear formatting rule for all commit messages. One sentence is sufficient to capture it.

---

## Step 3: Impact Scan

```
Impact Scan Results:
- Conflicts: None. The existing Git Sync Protocol in CLAUDE.md uses `git commit -m "<brief description>"`
  which is format-agnostic — it does not contradict conventional commits, it just doesn't enforce a format.
- Overlaps: None. No existing rule or skill covers commit message formatting.
- Gaps: This is genuinely new — no current rule specifies commit message format.
- Stale: None. Nothing needs to be replaced.
```

Note: The Git Sync Protocol example (`git commit -m "<brief description>"`) could optionally be updated to show a conventional commits example, but it's not strictly necessary since the new rule would apply globally.

---

## Step 4: Digestion Recommendation

```
Recommendation: Path B — Add rule to CLAUDE.md "Learned Rules" section
Reason: This is a single behavioral convention that distills into one sentence.
        It applies globally across all projects and sessions.
        It doesn't require a workflow, scripts, or reference material — just a rule.
        Path A is wrong (this is not general knowledge — it's a personal preference).
        Path C is wrong (no existing skill to extend).
        Path D is wrong (too lightweight for a kb/ entry).
        Path E is wrong (a single rule doesn't need a skill).
Expected effect: All future git commit messages will follow the format: type(scope): description
                 (e.g., "feat(render): add shadow cascade debug view", "fix(gi): correct LPV injection offset")
Risk: Minimal. The convention is well-established and non-controversial.
```

---

## Step 5: Execute Digestion

**Path B confirmed.** Appending the following rule to `~/.claude/CLAUDE.md` under "Learned Rules":

```
- **Conventional Commits**: Always use conventional commits format for git commit messages: `type(scope): description`. Common types: feat, fix, refactor, docs, test, chore, ci, perf, style. Scope is optional but encouraged.
```

Then executing Git Sync Protocol:
```bash
cd ~/.claude && git add -A && git commit -m "eat: add conventional commits rule to Learned Rules" && git push
```

---

Done. From now on, all git commit messages I write will follow conventional commits format, e.g.:

- `feat(render): add volumetric cloud temporal reprojection`
- `fix(gpu-driven): correct indirect draw arg buffer offset`
- `refactor(shader-sharp): simplify AST node visitor pattern`
- `docs: update CLAUDE.md with conventional commits rule`
