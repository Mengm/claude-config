# Deep Analysis Framework

When analyzing input for /eat, evaluate across these six dimensions. Not every dimension needs deep analysis — spend time proportional to the complexity of the input.

## 1. What — Core Value Extraction

- What is the central insight or technique?
- What specific problem does it solve?
- Are there novel patterns, architectures, or approaches?
- Strip away the narrative — what's the executable kernel?

For code: focus on the design patterns, not the implementation details.
For articles: identify the thesis and supporting evidence, ignore filler.
For repos: look at architecture decisions, not boilerplate.

## 2. When — Applicability & Frequency

- In what scenarios would this knowledge be useful?
- How often would those scenarios arise? (daily / weekly / monthly / rarely)
- Is this tied to a specific tech stack, or is it universal?
- Does it apply to the user's current workflow or is it aspirational?

High frequency + high relevance → strong candidate for CLAUDE.md rule or skill extension.
Low frequency + high value → kb/ entry or reference document.
Low frequency + low value → don't eat.

## 3. How — Implementation Shape

- Is this a single rule/convention? → CLAUDE.md
- Is this a multi-step workflow? → Skill candidate
- Is this reference material to consult on demand? → kb/ or skill reference
- Does it need scripts or automation? → Skill with scripts/

The implementation shape directly maps to the digestion path:
- Rule → Path B
- Workflow → Path E (or Path C if extending existing)
- Reference → Path D
- Script → Path E

## 4. Overlap — Relationship to Existing Capabilities

Compare against:
- Every rule in `~/.claude/CLAUDE.md`
- Every skill description in `~/.claude/skills/*/SKILL.md`
- Any relevant kb/ entries or memory files

Overlap categories:
- **Conflict**: New knowledge contradicts existing rule → Must resolve (update or reject)
- **Subsume**: New knowledge is a superset of existing → Replace/upgrade existing
- **Subset**: Existing capability already covers this → Don't eat (Path A)
- **Complement**: Fills a gap in existing capability → Extend (Path C)
- **Orthogonal**: Completely new territory → New skill or kb/ entry

## 5. Shelf-life — Knowledge Temporality

- **Evergreen**: Design principles, architectural patterns, human conventions → High priority
- **Long-lived**: Framework-specific patterns (stable frameworks) → Medium priority
- **Medium-lived**: API patterns, library-specific knowledge → Lower priority, check version
- **Short-lived**: Specific version workarounds, temporary hacks → Generally don't eat
- **Expired**: Deprecated APIs, outdated practices → Definitely don't eat

When shelf-life is uncertain, ask: "Will this still be true in 6 months?" If no, it's probably not worth internalizing.

## 6. Actionability — From Knowledge to Decision

Rate on a spectrum:

```
Decision rule  >  Workflow step  >  Heuristic  >  Reference  >  Background  >  Trivia
(most actionable)                                                        (least actionable)
```

- **Decision rule**: "When X, do Y because Z" → Directly executable, high value
- **Workflow step**: Part of a repeatable process → Skill-worthy if frequent
- **Heuristic**: "Generally prefer X over Y" → Good CLAUDE.md rule
- **Reference**: "Here's how API X works" → kb/ entry
- **Background**: "The history of why X exists" → Usually don't eat
- **Trivia**: Interesting but not actionable → Don't eat

## Output Template

After analysis, present findings in this format:

```
## Analysis: [title/topic]

**Core value**: [1-2 sentences]
**Knowledge type**: [rule / workflow / reference / pattern / tool]
**Applicability**: [when useful] — Frequency: [daily/weekly/monthly/rare]
**Shelf-life**: [evergreen / long / medium / short]
**Actionability**: [decision rule / workflow / heuristic / reference / background]
**Overlap**: [conflicts/complements/orthogonal to existing capabilities]

**Key takeaway**: [the single most important thing to internalize]
```
