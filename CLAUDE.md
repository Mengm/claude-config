# Personal Rules

## Self-Correction Protocol

When the user corrects any mistake, immediately write a rule to prevent it from recurring:
1. Analyze the root cause of the correction
2. Distill the lesson into a concise, actionable rule
3. Append it to the "Learned Rules" section of this file
4. Strictly follow all recorded rules going forward

## Knowledge Digestion Protocol

When absorbing external knowledge (articles, code, GitHub repos, others' Skills), decide the digestion format first:

1. **Existing Skill covers 80%+** → Extend the existing Skill, do not create a new one
2. **A single rule suffices** → Append to CLAUDE.md, do not build a Skill
3. **Requires script + reference docs + trigger routing** → Create a new Skill
4. **General knowledge Claude already knows** → Do not absorb
5. **One-off knowledge** → Do not absorb

Workflow: Identify input → Deep analysis → Impact scan (check for conflicts/overlaps with existing Skills/CLAUDE.md) → Propose digestion plan → Execute after user confirmation

Core principle: **The goal of digestion is to distill the essence, not to accumulate quantity.**

## Git Sync Protocol

After every modification to personal Agent config (CLAUDE.md, skills/, settings.json, hooks/), automatically run:
```
cd ~/.claude && git add -A && git commit -m "<brief description>" && git push
```
No user confirmation needed — modify and sync immediately.

## Writing Style

- **Critical instructions must be written in English** for precision and token efficiency.
- Descriptive/contextual content may use Chinese for readability.

## Learned Rules

（纠正后自动追加）
