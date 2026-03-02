# Role: Project Status Reporter

Print a concise project status dashboard. Read the governance files and report the current state — do not modify any files.

## First Steps

1. Read `TASKS.md` — identify current stage, task statuses
2. Read `REVIEWS.md` — check review pipeline status
3. Read `VERSION` — current version
4. Read `JOURNAL.md` — last few entries for recent activity context

## Output Format

```
## Project Status

- **Project:** Newton
- **Version:** [from VERSION file]
- **Current Stage:** Stage [N] — [stage name]
- **Branch:** [current git branch]

### Progress

| Status | Count |
|--------|-------|
| DONE | [X] |
| IN_PROGRESS | [X] |
| TODO | [X] |
| BLOCKED | [X] |

### Last Completed Task
- [T-Nnn] — [task name] (v[version])

### Next Task
- [T-Nnn] — [task name]

### Next Steps
[Context-aware recommendation based on current state:]
- If tasks remain: "Run `/task` to start [T-Nnn] — [task name]"
- If all impl tasks done but no review: "All implementation tasks complete. Run `/review` to start the review pipeline."
- If review done but no red-review: "Run `/red-review` for the adversarial review."
- If red-review done but no stage-report: "Run `/stage-report` to compile the unified report."
- If stage report pending approval: "Stage report is PENDING. Review and approve in REVIEWS.md."
- If stage report approved but gate not run: "Run `/task T-NG` to execute the stage gate."
- If fix tasks exist: "Remediation tasks need attention. Run `/task` to work on fixes."
- If stage complete: "Stage [N] complete. Run `/stage-init` to initialize Stage [N+1]."

### Recent Activity
[Last 3-5 journal entries from JOURNAL.md, if available]
```

## Log to Journal

Add an entry to `JOURNAL.md`:
```
| [date time] | Stage N / — | /project-status | Displayed project status dashboard |
```

## What You Never Do

- Modify any files (except JOURNAL.md for logging)
- Make recommendations not grounded in the actual state of governance files
- Skip reading any of the governance files

$ARGUMENTS
