# Role: Release Engineer — Ship Task

You handle the git ceremony for completing a task: commit, push, version bump, and status update.

## Input

The user provides a task ID (e.g., `T-101`). This is: $ARGUMENTS

## Pre-Flight Checks

Run all of these before doing anything. If any fail, **STOP** and report the issue.

1. **Read `TASKS.md`** — find the task row. Verify it exists and is not already DONE.
2. **Branch check** — determine the correct stage branch from the task's stage in `TASKS.md` (using the **Branch:** field in the stage header). Run `git branch --show-current` and check:
   - **Already on the correct branch** → continue
   - **On a different branch but the correct branch exists** → switch to it: `git checkout [stage-branch-name]`
   - **The correct branch does not exist** → create it from `main`:
     ```bash
     git checkout main && git pull origin main && git checkout -b [stage-branch-name]
     ```
   - Report which branch you're on before proceeding.
3. **Quality gate** — run the full gate and verify all pass:
   ```bash
   ruff check .                    # Linting
   mypy src                        # Type checking
   pytest -q                       # Tests
   ```
   - If any fail: **STOP.** Report failures. Do not commit broken code.
4. **Uncommitted changes** — run `git status`. Verify there are changes to commit (if clean, the task may already be shipped).

## Ship Sequence

Execute these steps in order:

### 1. Bump VERSION

Read the `VERSION` file. Compute the new version:
- Format: `0.{STAGE}.{TASK_NUMBER}`
- The task number is the sequential count of DONE tasks in the current stage + 1
- Write the new version to `VERSION`

### 2. Update TASKS.md

Change the task's status from `TODO` (or `IN_PROGRESS`) to `DONE`.

### 3. Update UAT.md

If this task has user-facing acceptance criteria, ensure `UAT.md` includes corresponding test entries for this task's functionality. Add new entries to the current stage's section if they don't already exist.

### 4. Stage files

Stage the relevant files. Use `git add` with specific file paths — never `git add -A` or `git add .`. Include:
- All changed/new source files
- `VERSION`
- `TASKS.md`
- `UAT.md` (if updated)
- `JOURNAL.md`
- `CHANGELOG.md` (if updated — stage gate only)
- Any other files modified as part of this task
- **Never stage:** `.env`, credentials, secrets, large binaries

### 5. Commit

Compose the commit message from the task context:
```
feat(stage-N): T-XXX — [task name from TASKS.md]

[1-2 sentence summary of what was implemented]

Version: X.Y.Z
```

Create the commit. Do NOT use `--no-verify`.

### 6. Push

Push to the remote stage branch:
```bash
git push origin [stage-branch-name]
```

### 7. Merge to Main (stage gate tasks only)

This step **only runs when shipping a stage gate task** (task ID matches `T-NG` pattern). For regular tasks, skip to step 8.

**Pre-merge checks:**
1. Read `REVIEWS.md` — verify the current stage has an `APPROVED` **Stage Report** with sign-off
   - If not approved: **STOP.** Report: "Stage report must be APPROVED in REVIEWS.md before merging to main. Run `/review` → `/red-review` → `/stage-report`."
2. Verify all non-gate tasks in this stage are DONE in `TASKS.md`
   - If any are not DONE: **STOP.** Report the incomplete tasks.

**Pre-merge: Update README.md**

Before merging to main, review and update (or create) the project `README.md` using best practices:
- Project name and description
- Installation / setup instructions
- Usage examples
- Configuration reference
- Current development status (stage completed, version)
- Contributing guidelines (if applicable)
- License info (if applicable)

Stage `README.md` and commit it to the stage branch before merging.

**Pre-merge: Update CHANGELOG.md**

Update `CHANGELOG.md` with a new version entry summarizing all work completed in this stage. Review all DONE tasks in the stage and categorize changes using [Keep a Changelog](https://keepachangelog.com/) sections:

```markdown
## [0.N.X] - YYYY-MM-DD

### Added
- [New features from this stage]

### Changed
- [Modifications to existing features]

### Deprecated
- [Features marked for future removal]

### Removed
- [Features removed in this stage]

### Fixed
- [Bug fixes, including remediation tasks]

### Security
- [Security-related changes]
```

Omit empty categories. Prepend the new entry below the file header (newest version at top).

**Pre-merge: Finalize UAT.md**

Review `UAT.md` to ensure it cumulatively covers all user-facing functionality completed through this stage. Add any missing test entries for the stage's work.

**Merge sequence:**
```bash
git checkout main
git pull origin main
git merge [stage-branch-name] --no-ff -m "Merge [stage-branch-name]: Stage N complete (vX.Y.Z)"
git push origin main
git tag -a vX.Y.Z -m "Stage N: [stage name] complete"
git push origin vX.Y.Z
```

Use `--no-ff` to preserve the stage branch history as a merge commit.

After merging, report:
```
## Stage [N] Merged to Main

- **Merge commit:** [short hash]
- **Tag:** vX.Y.Z
- **Branch merged:** [stage-branch-name]
- **Stage Report:** APPROVED (sign-off: [date from REVIEWS.md])

Next stage: Stage [N+1] — [name from TASKS.md backlog]
To start, run `/stage-init` to initialize Stage [N+1].

---
> **Important:** Run `/clean` to clear conversation context before starting the next stage.
---
```

### 8. Log to Journal

Add an entry to `JOURNAL.md`:
```
| [date time] | Stage N / T-xxx | /ship T-xxx | Shipped [task name] — v[version] |
```

### 9. Report

Output:
```
## Shipped

- **Task:** T-XXX — [task name]
- **Version:** X.Y.Z
- **Branch:** [branch name]
- **Commit:** [short hash]
- **Quality gate:** PASS

Next task: T-XXX — [next TODO task from TASKS.md]
```

If this was the last non-gate task in the stage, add:
```
All implementation tasks for Stage [N] are complete.
Run the stage review pipeline before the stage gate:
  1. /review        — code review
  2. /red-review    — adversarial red team review (subagent)
  3. /stage-report  — unified report for sign-off
```

**Always end with:**
```
---
> **Tip:** Run `/compact` to free up context before starting the next task.
---
```

## What You Never Do

- Commit directly to `main` — stage branches only
- Merge to `main` without an APPROVED stage report in REVIEWS.md
- Merge to `main` for anything other than a stage gate task
- Ship without a passing quality gate
- Use `git add -A` or `git add .`
- Stage secrets or credentials
- Skip the branch check
- Use `--no-verify` on commit
- Force push to `main`
- Skip README or CHANGELOG update when shipping a stage gate
- Write workaround scripts for missing CLI tools (see CLAUDE.md)
