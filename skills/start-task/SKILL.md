---
name: start-task
description: "Git task workflow: stash current changes, create branch from latest mainline-2022, do the work, commit, push, and create GitLab MR. Trigger when user says 'start task', 'new task', 'start-task', or describes a new coding task to begin."
user_invocable: true
---

# Start Task Workflow

This skill manages the full lifecycle of a coding task with Git + GitLab.

## Input

User provides: `<task description>` (a brief description of what needs to be done)

## Phase 1: Branch Setup

Execute these steps in order:

1. **Save current work** (if any uncommitted changes exist):
   ```bash
   git stash push -m "auto-stash before new task"
   ```
   - If no changes, skip this step
   - Tell user what was stashed

2. **Update mainline-2022**:
   ```bash
   git checkout mainline-2022
   git pull origin mainline-2022
   ```
   - If pull fails, report error and stop

3. **Create task branch**:
   - Derive branch name from task description
   - Format: `fix/<short-kebab-case>` for bug fixes, `feat/<short-kebab-case>` for features, `refactor/<short-kebab-case>` for refactors
   - Keep branch name under 50 chars
   ```bash
   git checkout -b <branch-name>
   ```

4. **Confirm ready**: Tell user the branch is ready, then proceed with the actual task work.

## Phase 2: Do the Work

Perform the coding task as requested. This is the main work phase - read code, make changes, run builds/tests as needed.

## Phase 3: Commit & Push (after work is complete)

1. **Stage and commit**:
   ```bash
   git add -A
   git commit -m "<type>: <concise description>"
   ```
   - Use conventional commit format: `fix:`, `feat:`, `refactor:`, `chore:`, etc.
   - Write commit message in English
   - If multiple logical changes, make multiple commits

2. **Ask user for confirmation before pushing**, then:
   ```bash
   git push -u origin <branch-name>
   ```

3. **Create Merge Request** - ask user for confirmation first, then:
   ```bash
   glab mr create --target-branch mainline-2022 --title "<commit message>" --description "<detailed description of changes>" --no-editor
   ```
   - Title: same as primary commit message
   - Description: summarize what was changed and why (2-5 sentences)
   - If `glab` is not available, output the GitLab MR creation URL:
     `<repo-url>/-/merge_requests/new?merge_request[source_branch]=<branch>&merge_request[target_branch]=mainline-2022`

## Rules

- **Always confirm** before `git push` and `glab mr create`
- If build or tests fail, fix before pushing
- Never force push
- If the task branch already exists remotely, append a number suffix (e.g., `fix/shadow-culling-2`)
- If user says "skip MR" or "no MR", skip Phase 3 step 3
