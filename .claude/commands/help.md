# Newton Commands — Quick Reference

Print this reference. Do not read any files or perform any actions — just display the table below exactly as written.

---

## Task Workflow

| Command | Purpose | Example |
|---|---|---|
| `/stage-init` | Initialize a new stage (tasks, branch, version) | `/stage-init` or `/stage-init 2` |
| `/task` | Orchestrate a full task (architect → implement → test). Auto-picks next TODO if no argument. | `/task` or `/task T-101` |
| `/ship` | Commit, push, bump version, mark task DONE | `/ship T-101` |
| `/project-status` | Show current stage, progress, and next steps | `/project-status` |

## Role Personas

| Command | Purpose | Example |
|---|---|---|
| `/architect` | Plan an implementation (no code, just design) | `/architect design the auth system` |
| `/implement` | Implement code across the stack | `/implement build the user registration flow` |
| `/test` | Write tests and run the quality gate | `/test cover the auth module` |

## Quality & Governance

| Command | Purpose | Example |
|---|---|---|
| `/review` | Code review → writes to REVIEWS.md | `/review` |
| `/red-review` | Adversarial red team review (subagent, fresh context) → writes to REVIEWS.md | `/red-review` |
| `/stage-report` | Compiles both reviews into unified report (interviews you first) → sign-off doc | `/stage-report` |
| `/verify-fixes` | Verify remediation tasks were completed successfully | `/verify-fixes` |
| `/spec-check` | Validate implementation against SPEC.md | `/spec-check check Stage 1 acceptance criteria` |
| `/help` | Show this reference | `/help` |

## Typical Workflow

```
# Initialize a new stage
/stage-init             # Set up stage tasks, branch, and version

# Work through tasks
/task                   # Auto-picks next TODO task — plan, implement, and test
                        # Review the output, make any tweaks
/ship T-101             # Commit + push to stage branch
/compact                # Free up context before next task

... repeat for each task in the stage ...

# Stage review pipeline (run all three in order):
/review                 # Code review → REVIEWS.md
/red-review             # Adversarial review (subagent) → REVIEWS.md
/stage-report           # Interviews you, then compiles unified report → REVIEWS.md
                        # Sign off on the stage report

# If fixes needed:
/task                   # Fix tasks are batched automatically
/ship T-1nn-FIX1        # Ship each fix (or batched)
/verify-fixes           # Verify fixes without full re-review

# Stage gate
/task T-1G              # Run stage gate (test + spec-check only)
/ship T-1G              # Ships gate + updates README + merges to main
/clean                  # Clear context before starting next stage

# Next stage
/stage-init             # Initialize next stage
```

## Key Files

| File | Purpose |
|---|---|
| `SPEC.md` | Canonical specification (source of truth) |
| `DECISIONS.md` | Decision log (overrides spec where they conflict) |
| `TASKS.md` | Task queue, stage tracking, version reference |
| `REVIEWS.md` | Stage code review log (sign-off required before merge) |
| `VERSION` | Current version |
| `JOURNAL.md` | Dev journal — history of all commands and prompts |
| `UAT.md` | User acceptance tests (cumulative across stages) |
| `CHANGELOG.md` | Changelog in Keep a Changelog format (updated at each stage completion) |
| `README.md` | Project README (updated at each stage completion) |
