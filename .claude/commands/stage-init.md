# Role: Stage Initializer

You handle the full stage initialization ceremony: prerequisite checks, task generation, user approval, branch creation, and version setup.

## Input

The user may optionally provide a stage number. This is: $ARGUMENTS

If no argument is provided, determine the next stage automatically from `TASKS.md` (the stage after the last completed or current stage).

## First Steps

1. Read `TASKS.md` — identify all existing stages, their statuses, and the backlog
2. Read `SPEC.md` — understand the full project scope
3. Read `DECISIONS.md` — for applicable constraints
4. Read `docs/reviews/stage-{N-1}.md` (previous stage review file) — check stage approval status. Also check `REVIEWS.md` index for quick reference.
5. Determine which stage to initialize (from argument or auto-detect)

## Prerequisite Checks

### For Stage 1 (first stage):
- No prerequisite — Stage 1 can always be initialized
- Verify no Stage 1 section already exists in `TASKS.md`

### For Stage N (N > 1):
- Check `docs/reviews/stage-{N-1}.md` for a **Stage Report** with status `APPROVED`
- If not approved: **STOP.** Report: "Stage [N-1] must have an APPROVED stage report before initializing Stage [N]. Run the review pipeline: `/review` → `/red-review` → `/stage-report`, then sign off."
- Verify the previous stage's gate task is `DONE` in `TASKS.md`
- Verify the previous stage branch has been merged to `main`

## Task Generation

### For existing project bootstrap (Stage 1 with Baseline Audit):

If `docs/reviews/baseline-audit.md` exists, use its findings to generate Stage 1 tasks:
- Critical and High findings become fix/improvement tasks
- Medium findings can be included at the user's discretion
- Group related findings into single tasks where it makes sense
- Add any setup tasks needed (e.g., adding missing test infrastructure, CI config)

### For all stages:

Using `SPEC.md` and the backlog entry for this stage:

1. **Identify all work items** needed to complete this stage's goals
2. **Break them into small, testable tasks** with clear acceptance criteria
3. **Assign task IDs** using the scheme: `T-N01`, `T-N02`, ... where N is the stage number
4. **Determine scope** for each task: `server`, `client`, `fullstack`, `docs`, `infra`
5. **Add a stage gate task** with ID `T-NG` (e.g., `T-1G` for Stage 1)
6. **Include acceptance criteria** derived from SPEC.md for every task

Propose the full task list in this format:

```
## Stage N: [Stage Name]

**Branch:** `stage/N-[stage-name]`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-N01 | [task description] | [scope] | [acceptance criteria] | TODO |
| T-N02 | [task description] | [scope] | [acceptance criteria] | TODO |
| ... | ... | ... | ... | TODO |
| T-NG | Stage gate: tests/lint/type/security | fullstack | All stage exit criteria pass | TODO |
```

## User Approval

**Present the full stage definition to the user and wait for sign-off before proceeding.**

Show:
1. Stage number and name
2. Branch name
3. Complete task table with IDs, descriptions, scopes, and acceptance criteria
4. Starting version number

Ask: "Does this stage plan look good? Any tasks to add, remove, or modify?"

**Do NOT proceed until the user approves.**

## After Approval

Execute these steps in order:

### 1. Update TASKS.md

- Insert the approved stage section into `TASKS.md` (before the Backlog section)
- Update the backlog: remove or mark the initialized stage entry as active
- Update the Version Reference table with the new stage start version

### 2. Update VERSION

Set version to `0.{STAGE}.0` (e.g., `0.1.0` for Stage 1, `0.2.0` for Stage 2).

### 3. Branch Creation

```bash
git checkout main
git pull origin main
git checkout -b stage/{N}-{stage-name}
```

### 4. Commit + Push

Stage and commit the updated files:

```bash
git add TASKS.md VERSION
git commit -m "stage-init: Stage {N} — {stage-name}

Initialized stage with task list derived from SPEC.md.

Version: 0.{STAGE}.0"
git push -u origin stage/{N}-{stage-name}
```

### 5. Log to Journal

Add an entry to `JOURNAL.md`:
```
| [date time] | Stage N / — | /stage-init | Initialized Stage N: [stage-name] with [X] tasks |
```

### 6. Report

```
## Stage [N] Initialized

- **Stage:** [N] — [stage name]
- **Branch:** stage/[N]-[stage-name]
- **Version:** 0.[N].0
- **Tasks:** [count] implementation tasks + 1 stage gate
- **First task:** T-[N]01 — [task name]

Run `/task` to start the first task.
```

## What You Never Do

- Initialize a stage without checking prerequisites (previous stage approved)
- Generate tasks without reading SPEC.md
- Proceed without user approval of the task list
- Skip branch creation or version setup
- Initialize a stage that already exists in TASKS.md

$ARGUMENTS
