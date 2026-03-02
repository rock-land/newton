# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Bootstrap Status: UNCUSTOMIZED

**If you see this section, this project was created from a template and has not been set up yet.**

When the user first opens this project (or asks you to set it up, or asks you to start work), run the bootstrap process:

### Bootstrap Process (New Project)

1. **Read `SPEC.md`** — this is the canonical specification the user has placed in the project root
2. **Read all governance files** — `TASKS.md`, `DECISIONS.md`, `REVIEWS.md`, `VERSION`
3. **Read all command files** in `.claude/commands/` to understand the workflow system
4. **Customize ALL files** based on what you learn from SPEC.md:
   - **This file (`CLAUDE.md`)** — fill in Project Overview, Commands, Architecture, Key Decisions; delete this Bootstrap section when done
   - **`TASKS.md`** — set up the template (do NOT populate Stage 1 tasks yet — that happens via `/stage-init`)
   - **`DECISIONS.md`** — record foundational decisions (tech stack, architecture patterns, quality standards, git workflow)
   - **`.claude/commands/*.md`** — replace `{PROJECT_NAME}`, fill in all `<!-- CUSTOMIZE: -->` sections with project-specific details
   - **`.claude/settings.local.json`** — add permission whitelist entries for your quality gate commands (lint, typecheck, test)
5. **Present the setup to the user for review** before starting implementation work
6. **Prompt the user to run `/stage-init`** to initialize Stage 1 with tasks derived from the spec
7. **Delete this Bootstrap section** from CLAUDE.md after customization is complete

The template uses `{PROJECT_NAME}` as a placeholder throughout — replace it everywhere.

### Bootstrap Process (Existing Project)

If bootstrapping an **existing project** (source code already exists, no governance files), OR if the user runs `/bootstrap-existing`:

1. **Copy bootstrap files** into the project (CLAUDE.md, TASKS.md, DECISIONS.md, REVIEWS.md, VERSION, .claude/commands/*)
2. **Review the existing project** — read all source files, understand the architecture, tech stack, patterns, and current state
3. **Customize all files** based on what you learn:
   - **`CLAUDE.md`** — fill in Project Overview, Commands, Architecture, Key Decisions from the actual codebase
   - **`TASKS.md`** — write a summary of completed work to date (no need to retroactively create stages/tasks). The first stage can address any issues found during review before commencing new feature development
   - **`DECISIONS.md`** — record existing architectural decisions discovered in the codebase
   - **`REVIEWS.md`** — perform a **Baseline Audit** of the codebase and write structured findings (these feed into Stage 1 task generation via `/stage-init`)
   - **`.claude/commands/*.md`** — replace `{PROJECT_NAME}`, fill in CUSTOMIZE sections with project-specific details
   - **`.claude/settings.local.json`** — add permission whitelist entries for quality gate commands
4. **Present the setup to the user for review**
5. **Prompt the user to run `/stage-init`** to initialize the first governance stage
6. **Delete this Bootstrap section** from CLAUDE.md after customization is complete

---

## Project Overview

<!-- CUSTOMIZE: Replace with a 2-3 sentence project description from SPEC.md. Include what the app does, who it's for, and what makes it distinctive. -->

{PROJECT_NAME} is [brief description]. The canonical specification is `SPEC.md`. Decision precedence: `DECISIONS.md` > `SPEC.md`.

**Current status:** Stage 1 in progress (v0.1.0).

## Commands

<!-- CUSTOMIZE: Replace with your project's actual commands. These are the commands Claude and you will run frequently. -->

```bash
# Quality checks (run before committing)
# [linter] .                # Linting
# [type-checker] src        # Type checking
# [test-runner] -q          # All tests
# [test-runner] --cov       # Tests with coverage

# Development server
# [command to start dev server]

# Database (if applicable)
# [command to start database]
# [command to initialize schema]

# Client (if applicable)
# cd client && npm install && npm run build && npm start
```

## Code Quality Configuration

<!-- CUSTOMIZE: List your linter, type checker, test runner, and their config files. -->

- **Linter:** [tool] — [key settings] ([config file])
- **Type checker:** [tool] — [key settings] ([config file])
- **Test runner:** [tool] — [key settings] ([config file])
- **Coverage targets:** >=80% global; 100% branch on critical modules

## Architecture

<!-- CUSTOMIZE: Document your tech stack, key abstractions, directory structure, and design patterns. This section is critical — it's what Claude reads to understand how to write code that fits your project. -->

**Stack:** [languages / frameworks / databases / key libraries]

### Key abstractions

<!-- List your protocol/interface classes and where they live. -->

### Configuration-driven design

<!-- List config file locations and precedence rules. -->

### API structure (if applicable)

<!-- Describe API conventions, endpoint structure, auth patterns. -->

## Key Decisions

<!-- CUSTOMIZE: Reference the most impactful entries from DECISIONS.md that affect daily development. -->

- **DEC-001:** [decision summary]

## Git Workflow

- `main` branch: always deployable
- Stage branches: `stage/{N}-{name}` (e.g., `stage/1-foundation`)
- Commit + push to stage branch on task completion; merge to `main` at stage completion only

## Versioning

Format: `0.{STAGE}.{TASK}` (current: 0.1.0). Version tracked in `VERSION` file.

## Task ID Scheme

- Stage 1 tasks: `T-101`, `T-102`, ... `T-1nn`
- Stage 2 tasks: `T-201`, `T-202`, ... `T-2nn`
- Stage gate tasks: `T-1G` (Stage 1 gate), `T-2G` (Stage 2 gate), etc.
- Remediation/fix tasks: `T-1nn-FIX1`, `T-1nn-FIX2`, etc. (appended to end of relevant stage)

## Dev Journal

Every slash command invocation and every free-form user prompt (except system commands like `/clear`, `/compact`, `/context`, `/status`) MUST be logged to `JOURNAL.md`. Format:

```
| YYYY-MM-DD HH:MM | Stage N / T-xxx | /command | One-sentence summary |
```

Entries are sorted descending (most recent at top). Log the entry at the START of command execution so it captures what was attempted.

## Missing CLI Tools

**NEVER** write workaround scripts, shims, or inline alternatives when a required command-line tool is not installed. If a command is not found:

1. **STOP** — do not attempt to work around the missing tool
2. **Tell the user** which tool is missing and what it's needed for
3. **Ask the user** whether they want to install it, use an alternative, or cancel
4. This applies to all commands: build tools, linters, formatters, database CLIs, package managers, etc.
