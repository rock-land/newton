# Role: Existing Project Bootstrap

You bootstrap the claude-bootstrap governance system onto an existing project that already has source code. This is the standalone command for setting up governance on a project that's already in development.

## When to Use

- The project already has source code, dependencies, and possibly a running application
- No governance files exist yet (no TASKS.md, DECISIONS.md, REVIEWS.md, etc.)
- The user wants to bring structure and governance to an ongoing project

## First Steps

1. **Survey the project** — read the directory structure, key source files, config files, package manifests, and any existing documentation
2. **Identify the tech stack** — languages, frameworks, databases, build tools, linters, test runners
3. **Understand the architecture** — patterns, abstractions, API structure, database schema
4. **Check for existing quality tools** — linters, formatters, type checkers, test suites, CI configs
5. **Note any issues** — code smells, missing tests, inconsistencies, security concerns

## Bootstrap Execution

### 1. Customize CLAUDE.md

Fill in all sections based on what you discovered:
- Project Overview (from existing README, package.json, or code inspection)
- Commands (actual build/test/lint commands from the project)
- Code Quality Configuration (existing linter/type checker/test runner configs)
- Architecture (actual tech stack, abstractions, directory structure)
- Key Decisions (inferred from the codebase)
- Delete the Bootstrap Status section

### 2. Customize TASKS.md

- Write a **Summary of Completed Work** section documenting what exists in the project
- Do NOT retroactively create stages or tasks for past work
- Set up the backlog with planned stages for future work
- The first stage can focus on addressing issues found during the review (tech debt, missing tests, security fixes) before new feature development

### 3. Customize DECISIONS.md

Record architectural decisions discovered in the codebase:
- Tech stack choices and rationale (inferred)
- Patterns and conventions already established
- Any constraints visible in the code (e.g., specific DB choice, API versioning scheme)

### 4. Baseline Audit → REVIEWS.md

Perform a structured audit of the existing codebase and write the findings to `REVIEWS.md` as a **Baseline Audit**. This is not a stage review — it's a one-time assessment of the project's current state that feeds into Stage 1 task generation.

Run the quality gate (if tools are available) and then audit:

- **Code quality** — linting issues, type errors, dead code, inconsistent patterns
- **Security** — input validation gaps, hardcoded secrets, injection risks, dependency vulnerabilities
- **Test coverage** — missing tests, weak assertions, untested critical paths
- **Architecture** — circular dependencies, leaky abstractions, config issues, performance risks
- **Spec compliance** — if SPEC.md exists, check how the code aligns with it
- **Tech debt** — TODO/FIXME comments, deprecated dependencies, workarounds

Write to `REVIEWS.md` in this format:

```markdown
## Baseline Audit

- **Date:** YYYY-MM-DD
- **Scope:** Full codebase audit (pre-governance)

### Quality Gate
- lint: PASS/FAIL/N/A (details)
- types: PASS/FAIL/N/A (details)
- tests: PASS/FAIL/N/A — coverage XX%

### Critical Findings (must address in Stage 1)
- [BA-C1] **[file:line]** Description — impact

### High Findings (should address in Stage 1)
- [BA-H1] **[file:line]** Description — impact

### Medium Findings (recommend addressing)
- [BA-M1] **[file:line]** Description

### Low Findings (informational)
- [BA-L1] **[file:line]** Description

### Positive Observations
[What's done well in the existing codebase]

### Recommended Stage 1 Focus
[Summary of what Stage 1 should prioritize based on the audit]
```

This audit is referenced by `/stage-init` when generating Stage 1 tasks for an existing project.

### 5. Customize all command files

- Replace `{PROJECT_NAME}` everywhere
- Fill in `<!-- CUSTOMIZE: -->` sections with project-specific details
- Set up quality gate commands with the actual project tools

### 6. Update .claude/settings.local.json

Add permission whitelist entries for the project's actual quality gate commands.

### 7. Set up JOURNAL.md and UAT.md

Create both files with project-appropriate headers.

### 8. Set VERSION

Set to `0.1.0` (starting governance from Stage 1).

## Present to User

Show the user a summary of:
1. What was discovered about the project
2. Key decisions recorded
3. Issues noted (potential first-stage work)
4. Proposed backlog stages
5. Suggested first stage focus

**Wait for user approval before committing any files.**

## After Approval

1. Commit all governance files
2. Prompt the user to run `/stage-init` to initialize the first governance stage

## Log to Journal

Add an entry to `JOURNAL.md`:
```
| [date time] | — / — | /bootstrap-existing | Bootstrapped governance onto existing project |
```

## What You Never Do

- Delete or modify existing source code during bootstrap
- Create retroactive stages/tasks for work already done
- Assume the project structure without reading files
- Skip presenting the setup to the user for review
- Write workaround scripts for missing CLI tools (see CLAUDE.md)

$ARGUMENTS
