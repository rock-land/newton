# {PROJECT_NAME} Decisions Log

Purpose: Record key engineering/product decisions and rationale to prevent drift and re-litigation.

Format:
- ID: DEC-XXX
- Date
- Decision
- Context
- Consequences
- Status: Proposed / Accepted / Superseded

<!--
BOOTSTRAP NOTE (for Claude):

When setting up a new project, seed this file with foundational decisions derived from:
1. The tech stack chosen (language, framework, database, etc.)
2. Architectural patterns from SPEC.md (monolith vs microservices, API style, etc.)
3. Quality standards (linting rules, coverage targets, type checking strictness)
4. Git workflow (stage branches, merge strategy)
5. Any constraints the user specifies during setup

Typical early decisions to record:
- Tech stack selection and rationale
- Config-driven design (if applicable)
- Git workflow and branch strategy
- Quality gate standards
- Client framework choice (if applicable)
- Deployment target and constraints
-->

---

## DEC-001
- **Date:** YYYY-MM-DD
- **Decision:** `SPEC.md` is the canonical specification. Decision precedence: `DECISIONS.md` > `SPEC.md`.
- **Context:** A single source of truth prevents ambiguity and spec drift.
- **Consequences:** Implementation must follow SPEC.md unless a decision log entry explicitly overrides it.
- **Status:** Accepted

## DEC-002
- **Date:** YYYY-MM-DD
- **Decision:** Git workflow enforces stage branches with push on each task completion.
- **Context:** Avoid local-only drift and ensure progress is auditable.
- **Consequences:** On each task marked DONE, commit + push to current stage branch; merge to `main` only at stage completion.
- **Status:** Accepted
