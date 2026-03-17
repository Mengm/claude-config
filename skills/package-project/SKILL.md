---
name: package-project
description: >
  Trigger project packaging (T3 Default PC Build) on jn-workflow CI. Connects to
  user's system Chrome via CDP (no SSO needed). Selects engine branch and triggers
  default PC package build. Trigger when user says "package project", "打包项目",
  "触发打包", "trigger package", "出包", or /package-project.
---

# Package Project Skill

Trigger a T3 project package build (StandaloneWindows64) on jn-workflow.bytedance.net.

## Prerequisites

- Chrome must be running with `--remote-debugging-port=9222`
- If not, run: `cd ~/.claude/scripts && node chrome-start.js`
- Engine build must be completed first (engine branch available in dropdown)

## Execution Steps

1. Ask the user for the engine branch name.
   - Usually shown in the feishu notification from engine build.

2. Show confirmation:
   - Engine Branch: (user provided)
   - Package Type: 默认PC包
   - Target: StandaloneWindows64

3. After user confirms, run:
   ```bash
   cd ~/.claude/scripts && node trigger-project-package.js "<engine_branch>"
   ```

4. Options:
   - `--dry-run`: Preview without submitting

5. Report the package URL to the user.

6. Remind user: "Package build takes ~10 minutes. You'll get a feishu notification when done."

## Script Location

`~/.claude/scripts/trigger-project-package.js`
