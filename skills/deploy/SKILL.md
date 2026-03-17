---
name: deploy
description: >
  Full deployment pipeline: push code, trigger engine build, then trigger project
  packaging. Semi-automated with user confirmation at each step. Trigger when user
  says "deploy", "部署", "全流程", "push and build", "推送并编译", or /deploy.
  Orchestrates /build-engine and /package-project skills.
---

# Deploy Pipeline Skill

Full CI/CD workflow: push -> engine build -> project package.

## Files in this skill

- `login.js` — SSO login helper, saves auth cookies to `~/.claude/playwright/jnworkflow-auth.json`

## Workflow

### Step 1: Push Code
1. Show `git status` and recent commits on current branch
2. Ask user to confirm push
3. Push to remote: `git push origin HEAD`

### Step 2: Trigger Engine Build
1. Get current branch name
2. Show build parameters and ask confirmation
3. Run:
   ```bash
   cd ~/.claude/skills/build-engine && node trigger.js <branch> --no-dev
   ```
4. Report build URL
5. Tell user: "Engine build triggered. Wait for feishu notification, then come back to trigger packaging."

### Step 3: Trigger Project Package (after user returns)
When user comes back saying engine build is done:
1. Ask for engine branch name (usually shown in feishu notification)
2. Show parameters and ask confirmation
3. Run:
   ```bash
   cd ~/.claude/skills/package-project && node trigger.js "<engine_branch>"
   ```
4. Report package URL

## Auth Prerequisite
If auth expired, run:
```bash
cd ~/.claude/skills/deploy && node login.js
```

## Notes
- Engine build takes ~10-15 minutes
- Project packaging takes ~10 minutes
- Both send feishu notifications on completion
- Use `--dry-run` to preview without submitting
