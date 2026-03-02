# {PROJECT_NAME} Development Tasks

**Current Version:** `0.1.0` (Stage 1, Task 0)
**Latest Release:** —

Status: Active
**Source of truth:** `SPEC.md`

## Version Reference

| Version | Stage | Milestone |
|---------|-------|-----------|
| 0.1.0 | 1 | Stage 1 start |

## Rules
- Work only from `SPEC.md` unless the lead explicitly approves deviation.
- Use TDD for every implementation task.
- Keep tasks small and testable.

## Task ID Scheme
- Stage N tasks: `T-N01`, `T-N02`, ... `T-Nnn` (e.g., `T-101` for Stage 1 task 1)
- Stage gate: `T-NG` (e.g., `T-1G` for Stage 1 gate)
- Fix tasks: `T-Nnn-FIX1`, `T-Nnn-FIX2` (appended at end of stage)

---

<!--
Stage sections are created by /stage-init. Do not manually add stages.
Each stage section is populated during stage initialization with tasks derived from SPEC.md.
-->

## Backlog

<!--
Backlog lists planned stages at a high level. Detailed tasks are generated
during /stage-init, NOT in advance. Keep entries lightweight.
-->

<!-- CUSTOMIZE: List planned stages from SPEC.md. Just stage number, name, and optional one-line summary. -->

| Stage | Name | Summary |
|-------|------|---------|
| 1 | [Stage Name] | [Optional one-line summary] |
| 2 | [Stage Name] | [Optional one-line summary] |

---

## Notes

- Keep task IDs stable for commit references.
- Update status values only: TODO / IN_PROGRESS / BLOCKED / DONE.
- Tasks within a stage are populated by `/stage-init`.
- Fix tasks are appended at the end of the relevant stage with `-FIXn` suffix.
