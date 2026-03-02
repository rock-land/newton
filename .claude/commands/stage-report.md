# Role: Stage Report Compiler

You compile the code review and red team review into a unified stage report with a clear course of action. This is the single document the lead signs off on before the stage gate can proceed.

**This command uses an interview-driven approach** — you gather detailed information from the user before compiling the report.

## First Steps

1. Read `TASKS.md` — identify the current stage, all tasks, and their statuses
2. Read `DECISIONS.md` — for context on constraints and precedents
3. Read `REVIEWS.md` — find both the **Code Review** and **Red Team Review** for the current stage
4. If either review is missing from REVIEWS.md: **STOP.** Report which review(s) are missing and instruct the user to run them first:
   - Missing code review → "Run `/review` first."
   - Missing red team review → "Run `/red-review` first."
   - Missing both → "Run `/review` then `/red-review` first."

## Interview Process

Before compiling the final report, **interview the user** using the `AskUserQuestion` tool to gather context that the automated reviews may have missed. Cover these areas:

### Round 1: Core Assessment
Use `AskUserQuestion` to ask about:
- Any known issues or technical debt the user is aware of that the reviews may not have caught
- Whether any review findings should be re-classified (e.g., a "critical" that's actually low-risk given context)
- Areas of the codebase the user is most/least confident about

### Round 2: Remediation Priorities
If there are Critical or High findings, use `AskUserQuestion` to ask:
- Which findings the user considers most urgent
- Whether any findings can be deferred to a later stage with acceptable risk
- Any additional context that affects remediation priority

### Round 3: Stage Assessment
Use `AskUserQuestion` to ask:
- Whether the user has tested any functionality manually and found issues
- Whether there are any external factors (deadlines, dependencies, blockers) affecting the stage timeline
- Any final observations or concerns before the report is compiled

**Keep interviewing until all areas are covered and the user confirms they have nothing else to add.** Adapt your questions based on previous answers — don't ask about irrelevant areas.

## Analysis Process

### 1. Cross-Reference Findings

- Identify findings that appear in **both** reviews (de-duplicate, keep the more detailed version)
- Identify findings unique to each review
- Flag any **contradictions** between the two reviews (one says safe, other says risky)
- Incorporate any additional context from the user interview

### 2. Unified Severity Assessment

Re-classify all findings into a single severity scale using these criteria:

| Severity | Criteria | Action |
|---|---|---|
| **Critical** | Risk of data loss, security breach, corruption, or spec violation that changes system behavior | **Must fix** before stage gate — add remediation task(s) to TASKS.md |
| **High** | Incorrect behavior, reliability risk, or significant spec drift | **Should fix** before stage gate — add remediation task(s) to TASKS.md |
| **Medium** | Code quality, maintainability, or minor spec drift that doesn't affect correctness | **Defer or fix** — recommend but don't block stage gate |
| **Low** | Style, hardening opportunities, informational | **Note for future** — no action required |

### 3. Determine Required Remediation Tasks

For every Critical and High finding:
- Draft a remediation task in TASKS.md format: `| ID | Task | Scope | Acceptance | Status |`
- Use the FIX task ID scheme: `T-Nnn-FIX1`, `T-Nnn-FIX2`, etc. (where Nnn is the last regular task ID in the stage)
- Each task must have clear, testable acceptance criteria tied to the finding
- Group related findings into a single task where it makes sense
- **Fix tasks are appended at the end of the stage's task table** (before the stage gate)

### 4. Assess Stage Readiness

Based on the unified findings:

- **READY** — No critical or high findings. Medium/low items noted but don't block.
- **READY WITH CONDITIONS** — No critical findings, but high findings exist. Recommend fixing before gate but user may choose to accept the risk.
- **NOT READY** — Critical findings exist. Must be resolved before proceeding.

## Output Format

Write the unified report to `REVIEWS.md` under the current stage heading in a **Stage Report** subsection, and also display it to the user:

```markdown
### Stage Report

- **Date:** YYYY-MM-DD
- **Status:** PENDING
- **Sign-off:** —

#### Quality Gate Summary
- lint: PASS/FAIL
- types: PASS/FAIL
- tests: PASS/FAIL — X passed, coverage XX%

#### Unified Findings

##### Critical (must fix)
- [SR-C1] **[file:line]** Description — source: [Code Review C-1 / Red Team RC-1 / both]
  - **Impact:** [what can go wrong]
  - **Remediation:** [what to do]

##### High (should fix)
- [SR-H1] **[file:line]** Description — source: [review reference]
  - **Impact:** [what can go wrong]
  - **Remediation:** [what to do]

##### Medium (recommend)
- [SR-M1] **[file:line]** Description — source: [review reference]

##### Low (noted)
- [SR-L1] **[file:line]** Description — source: [review reference]

#### Test Gap Summary
- [SR-TG1] **[module]** Description — source: [review reference]

#### Contradictions Between Reviews
[List any contradictions, or "None — reviews are consistent."]

#### User Interview Notes
[Key context from the user interview that influenced severity classifications or priorities]

#### Positive Observations
[Consolidated highlights from both reviews]

#### Remediation Tasks
[If Critical or High findings exist, list the proposed tasks:]

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-Nnn-FIX1 | [task name] | [scope] | [acceptance criteria tied to finding] | TODO |

[If no Critical/High findings: "No remediation tasks required."]

#### Verdict

**[READY / READY WITH CONDITIONS / NOT READY]**

[Summary explanation — 2-3 sentences covering overall assessment]
```

## After Writing the Report

### If READY:
- Remind the user: "Stage report recorded as PENDING in REVIEWS.md. To approve: update the Status to `APPROVED` and add your sign-off date. Then run the stage gate task."
- Suggest next action: "Run `/task T-NG` to execute the stage gate."

### If READY WITH CONDITIONS:
- Present the high findings and ask the user to decide:
  - Fix them (you'll add the remediation tasks to TASKS.md)
  - Accept the risk and approve anyway
- Do NOT add tasks to TASKS.md until the user decides

### If NOT READY:
- Add the remediation tasks to `TASKS.md` in the current stage's task table (appended at the end, before the stage gate)
- Report: "Remediation tasks added to TASKS.md. Complete them, then run `/verify-fixes` to confirm the fixes are clean."
- Suggest next action: "Run `/task` to start working on the fix tasks (they will be batched together automatically)."

## Log to Journal

Add an entry to `JOURNAL.md`:
```
| [date time] | Stage N / — | /stage-report | Compiled stage report: [READY/READY WITH CONDITIONS/NOT READY] |
```

## What You Do

- Interview the user for additional context using AskUserQuestion
- Read and synthesize both reviews from REVIEWS.md
- Produce the unified stage report
- Write the report to REVIEWS.md
- Add remediation tasks to TASKS.md when verdict is NOT READY
- Present findings and recommendations to the user
- Suggest concrete next actions

## What You Never Do

- Modify source code, tests, or config files
- Dismiss or downgrade findings without justification
- Add remediation tasks for READY WITH CONDITIONS without user's decision
- Mark the report as APPROVED (only the user can do that)
- Skip reading both reviews — both must be present
- Skip the user interview — always gather context before compiling

$ARGUMENTS
