---
name: build-engine
description: >
  Trigger Unity engine build on jn-workflow CI. Uses Playwright browser automation
  with saved SSO auth state. Fills branch name, selects build targets, and clicks
  build. Trigger when user says "build engine", "编译引擎", "触发引擎编译",
  "trigger engine build", or /build-engine. Requires prior SSO login via
  jnworkflow-login.js.
---

# Build Engine Skill

Trigger a Unity engine build on jn-workflow.bytedance.net.

## Prerequisites

- Playwright installed at `~/.claude/scripts/node_modules/playwright`
- Auth state saved at `~/.claude/playwright/jnworkflow-auth.json`
- If auth expired, run: `cd ~/.claude/scripts && node jnworkflow-login.js`

## Execution Steps

1. Get the current git branch name:
   ```bash
   git rev-parse --abbrev-ref HEAD
   ```

2. Show the user what will be built and ask for confirmation:
   - Branch: (current branch)
   - Build targets: WINDOWS_EDITOR + WINDOWS_STANDALONE_SUPPORT + ANDROID_PLAYER
   - Config: NO_DEV (default)

3. After user confirms, run the build script:
   ```bash
   cd ~/.claude/scripts && node trigger-engine-build.js <branch_name> --no-dev
   ```

4. Common options:
   - `--full-build`: Add FULL_BUILD flag (clears cache)
   - `--skip-smoketest`: Skip smoke test
   - `--headed`: Run with visible browser (for debugging)
   - `--dry-run`: Preview without submitting

5. Report the build URL to the user.

6. Remind user: "Build takes ~10-15 minutes. You'll get a feishu notification when done."

## If Auth Expires

If the script reports auth expired:
```bash
cd ~/.claude/scripts && node jnworkflow-login.js
```
Then retry the build command.

## Script Location

`~/.claude/scripts/trigger-engine-build.js`
