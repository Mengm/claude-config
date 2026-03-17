---
name: package-project
description: >
  Trigger project packaging (T3 Default PC Build) on jn-workflow CI. Uses Playwright
  browser automation with saved SSO auth state. Selects engine branch and triggers
  default PC package build. Trigger when user says "package project", "打包项目",
  "触发打包", "trigger package", "出包", or /package-project. Requires prior SSO
  login and a completed engine build.
---

# Package Project Skill

Trigger a T3 project package build (StandaloneWindows64) on jn-workflow.bytedance.net.

## Prerequisites

- Playwright installed at `~/.claude/scripts/node_modules/playwright`
- Auth state saved at `~/.claude/playwright/jnworkflow-auth.json`
- Engine build must be completed first (engine branch available in dropdown)

## Execution Steps

1. Ask the user for the engine branch name.
   - The engine build creates a branch like `UnityBuild_<original_branch>` or similar.
   - If user doesn't know, they can check the engine build page or feishu notification.

2. Show confirmation:
   - Engine Branch: (user provided)
   - Package Type: 默认PC包
   - Target: StandaloneWindows64

3. After user confirms, run:
   ```bash
   cd ~/.claude/scripts && node trigger-project-package.js "<engine_branch>" --headed
   ```

4. Options:
   - `--headed`: Run with visible browser (recommended first time)
   - `--dry-run`: Preview without submitting

5. Report the package URL to the user.

6. Remind user: "Package build takes ~10 minutes. You'll get a feishu notification when done."

## If Auth Expires

```bash
cd ~/.claude/scripts && node jnworkflow-login.js
```

## Script Location

`~/.claude/scripts/trigger-project-package.js`
