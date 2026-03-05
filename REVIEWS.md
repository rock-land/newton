# Newton Code Reviews

Review log for stage-level code audits. Each stage must have an APPROVED review before work begins on the next stage.

**Status values:** `PENDING` → `NEEDS_FIXES` → `APPROVED`
**Sign-off:** Only the project lead can set status to APPROVED.

## Review Files

Reviews are stored as individual files per stage in `docs/reviews/`:

| Stage | File | Status |
|-------|------|--------|
| Baseline Audit | [`docs/reviews/baseline-audit.md`](docs/reviews/baseline-audit.md) | Complete |
| Stage 1: Remediation & Hardening | [`docs/reviews/stage-1.md`](docs/reviews/stage-1.md) | APPROVED |
| Stage 2: Event Detection & Tokenization | [`docs/reviews/stage-2.md`](docs/reviews/stage-2.md) | APPROVED |
| Stage 3: ML Pipeline | [`docs/reviews/stage-3.md`](docs/reviews/stage-3.md) | APPROVED |
| Stage 4: UAT & Admin UI | [`docs/reviews/stage-4.md`](docs/reviews/stage-4.md) | APPROVED |
| Stage 5: Trading Engine | [`docs/reviews/stage-5.md`](docs/reviews/stage-5.md) | FIXES_VERIFIED |

<!--
Review files are populated automatically by the review pipeline:
  1. /review       — writes a Code Review subsection
  2. /red-review   — writes a Red Team Review subsection (via subagent)
  3. /stage-report — writes a Stage Report subsection (unified assessment)
  4. /verify-fixes — writes a Fix Verification subsection

For existing project bootstraps:
  /bootstrap-existing — writes docs/reviews/baseline-audit.md (one-time, pre-governance)
  This audit feeds into /stage-init for Stage 1 task generation.

Do not manually edit review content. Only the lead edits Status and Sign-off fields.

File naming convention: docs/reviews/stage-{N}.md
-->
