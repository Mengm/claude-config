---
name: build-engine
description: >
  Trigger Unity engine build on jn-workflow CI. Connects to user's system Chrome
  via CDP (no SSO needed). Fills branch name, selects build targets, and clicks
  build. Trigger when user says "build engine", "编译引擎", "触发引擎编译",
  "trigger engine build", or /build-engine.
---

# Build Engine Skill

Trigger a Unity engine build on jn-workflow.bytedance.net.

## Prerequisites

- Chrome must be running with `--remote-debugging-port=9222`
- If not, run: `cd ~/.claude/scripts && node chrome-start.js`

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
   - `--dry-run`: Preview without submitting

5. Report the build URL to the user.

6. Remind user: "Build takes ~10-15 minutes. You'll get a feishu notification when done."

## If Connection Fails

Chrome not running with debug port:
```bash
cd ~/.claude/scripts && node chrome-start.js
```

## Script Location

`~/.claude/scripts/trigger-engine-build.js`
