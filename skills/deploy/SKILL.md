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

## Workflow

### Step 1: Push Code
1. Show `git status` and recent commits on current branch
2. Ask user to confirm push
3. Push to remote:
   ```bash
   git push origin HEAD
   ```

### Step 2: Trigger Engine Build
1. Get current branch name
2. Show build parameters and ask confirmation
3. Run:
   ```bash
   cd ~/.claude/scripts && node trigger-engine-build.js <branch> --no-dev
   ```
4. Report build URL
5. Tell user: "Engine build triggered. Wait for feishu notification, then come back to trigger packaging."

### Step 3: Trigger Project Package (after user returns)
When user comes back saying engine build is done:
1. Ask for engine branch name (usually shown in feishu notification)
2. Show parameters and ask confirmation
3. Run:
   ```bash
   cd ~/.claude/scripts && node trigger-project-package.js "<engine_branch>" --headed
   ```
4. Report package URL

## Auth Prerequisite
If any step reports auth expired:
```bash
cd ~/.claude/scripts && node jnworkflow-login.js
```

## Notes
- Engine build takes ~10-15 minutes
- Project packaging takes ~10 minutes
- Both send feishu notifications on completion
- Use `--headed` flag to watch browser automation in action
- Use `--dry-run` to preview without submitting
