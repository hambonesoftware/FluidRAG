# agents.md — Multistep Codex Agent System

This file defines the **multi-agent workflow** Codex should use to execute **Phase 1** from `app_plan` and `app_finalstubs`. Each “agent” is a role with a clear contract (inputs, outputs, success criteria) and explicit handoffs. Codex may implement these roles sequentially within one run.

---

## 0) Shared Assumptions & Sources of Truth

* **Canonical plans folder:** `app_plan/`

  * `sequence_overall.md` — overall system architecture & flows
  * `finalstubs_latest.json` — *authoritative* file blueprints (paths, signatures, imports, declared types, docstrings)
  * `phases/phase_1.md` — Phase 1 scope, Definition of Done (DoD), acceptance tests
  * (optional) contracts, type maps, API schemas referenced by Phase 1
* **Authoritative stubs folder:** `app_finalstubs/` — per-file “final stubs” to materialize
* **If any conflict:** `finalstubs_latest.json` governs file structure & signatures; `phase_1.md` governs scope & acceptance.

**Non-negotiables**

* No partial files: only generate what you can fully finish to production-ready quality.
* Keep naming, imports, types, and file paths exactly as specified.
* Prefer a **vertical slice** (end-to-end feature) if Phase 1 is too large for one pass.

---

## Agent Roster

### 1) Planner

**Goal:** Build an actionable plan for Phase 1.

* **Inputs:**
  `app_plan/sequence_overall.md`, `app_plan/finalstubs_latest.json`, `app_plan/phases/phase_1.md`
* **Actions:**

  * Summarize the architecture and Phase 1 acceptance criteria.
  * Enumerate required files/modules for Phase 1.
  * If scope is too large, select the **largest complete vertical slice**.
* **Outputs:**

  * `PHASE_1_SCOPE.lock` (final file list + rationale)
  * A brief plan summary (printed in the run output)
* **Success:** Scope is implementable end-to-end **without placeholders** and matches DoD.

---

### 2) Reader

**Goal:** Normalize and cache the plan knowledge.

* **Inputs:** Same as Planner.
* **Actions:**

  * Extract contracts (interfaces, DTOs, endpoints, schemas) referenced by Phase 1.
  * Resolve any naming collisions or ambiguities **without altering** canonical names; record decisions in a short log.
* **Outputs:**

  * In-memory map: `{ file_path -> spec }` from `finalstubs_latest.json`
  * `logs/plan_read.log` (optional)
* **Success:** All Phase 1 files have clear, unambiguous specs.

---

### 3) Stub Materializer

**Goal:** Create the on-disk files exactly as declared.

* **Inputs:** Final scope, `finalstubs_latest.json`, `app_finalstubs/`
* **Actions:**

  * Generate each file’s structure, imports, docstrings, type signatures, comments, enums, exceptions, and empty method bodies **as defined**.
  * Include any helper files referenced by those stubs.
* **Outputs:**

  * Concrete files in repo (matching paths exactly)
  * `logs/materialization.log` (optional)
* **Success:** Tree mirrors `finalstubs_latest.json` for the selected scope; project builds.

---

### 4) Implementer

**Goal:** Fill method bodies to meet Phase 1 functionality.

* **Inputs:** Materialized files, Phase 1 requirements
* **Actions:**

  * Implement logic **only** within the Phase 1 scope.
  * If a dependency is out of scope, provide a **minimal adapter/fake** behind the declared interface.
  * Respect offline/online toggles (default **offline**).
* **Outputs:** Updated source with complete logic.
* **Success:** Feature(s) function locally and meet acceptance criteria.

---

### 5) Tester

**Goal:** Provide complete test coverage for public contracts added/changed in Phase 1.

* **Inputs:** Phase 1 DoD, finalstubs test entries (if any)
* **Actions:**

  * Generate tests (unit and, if required, small integration) covering sunny & error paths.
  * Use the project’s declared runner (read from plans); if unspecified, prefer common defaults:

    * Python: `pytest -q`
    * Node: `npm test` or `pnpm test`
  * Make tests deterministic (no network, seeded randomness).
* **Outputs:**

  * Test files under the project’s convention (e.g., `tests/`, `__tests__/`)
  * Recorded run output in `logs/test_results.log` (optional)
* **Success:** All tests pass locally for the Phase 1 slice.

---

### 6) Linter & Type-Checker

**Goal:** Enforce style, static checks, and type safety per plans.

* **Inputs:** Plans (linters/typing config), source code
* **Actions:**

  * Run configured tools (e.g., `ruff`/`flake8`/`black`, `mypy`/`pyright`, `eslint`/`tsc`).
  * Fix violations in-place; do not disable rules unless plans require it.
* **Outputs:** Clean lint/type report.
* **Success:** Zero blocking lint or type errors for Phase 1 files.

---

### 7) Integrator

**Goal:** Wire configs, feature flags, and adapters.

* **Inputs:** Source, Phase 1 acceptance criteria
* **Actions:**

  * Add config templates (e.g., `.env.example`) if referenced.
  * Implement **offline-first** flag: when OFF, all codepaths run without network.
  * Ensure new modules are imported/registered where needed (routers, DI containers, CLI, etc.).
* **Outputs:**

  * Updated configuration, minimal bootstrapping glue
  * `PHASE_1_NOTES.md` (what’s built, how to run/tests, flags)
* **Success:** Project can run the Phase 1 slice with a single command sequence.

---

### 8) Logger

**Goal:** Provide traceability for decisions and changes.

* **Inputs:** All previous agent outputs
* **Actions:**

  * Emit concise structured logs for planning decisions, scope selection, test summary.
  * Avoid sensitive data; prefer short, greppable lines.
* **Outputs:**

  * `logs/` (optional): `plan_read.log`, `materialization.log`, `test_results.log`
* **Success:** A developer can audit “what changed and why” in <5 minutes.

---

### 9) Committer

**Goal:** Commit only complete, passing work.

* **Inputs:** All files, passing tests, notes
* **Actions:**

  * Verify Acceptance Checklist (below).
  * Create a single commit with conventional message:

    ```
    feat(phase-1): implement <scope-summary> per app_plan

    - Implements: <file list>
    - Tests: <test files>
    - Accepts: <phase_1 criteria satisfied>
    - Notes: see PHASE_1_NOTES.md
    ```
* **Outputs:** One commit with only finished files.
* **Success:** No TODOs/placeholders; build + tests pass.

---

## Handoffs & Order of Operations

1. **Planner → Reader**: scope & acceptance captured
2. **Reader → Stub Materializer**: spec map → files
3. **Materializer → Implementer**: method bodies implemented
4. **Implementer → Tester**: tests authored & run
5. **Tester → Linter/Type-Checker → Integrator**: clean code & configs wired
6. **Integrator → Logger → Committer**: logs emitted, final commit

---

## Acceptance Checklist (hard gate)

* [ ] Files implemented **exactly** per `finalstubs_latest.json` (paths, names, signatures, imports, types).
* [ ] Scope completed end-to-end (no TODOs, no placeholders).
* [ ] All tests for Phase 1 slice **pass locally**.
* [ ] No blocking lint or type errors.
* [ ] `PHASE_1_SCOPE.lock` and `PHASE_1_NOTES.md` created and accurate.
* [ ] Offline toggle works; when OFF, no network requests occur.

---

## Failure & Recovery Protocols

* **Token/size limits:** Narrow to the largest coherent vertical slice and record rationale in `PHASE_1_SCOPE.lock`. Never leave partial files.
* **Missing dependency out of scope:** Introduce a **minimal adapter/fake** behind the declared interface; document in `PHASE_1_NOTES.md`.
* **Ambiguous contract:** Prefer `finalstubs_latest.json`. If still unclear, choose the least-surprising option and note it in the notes file.
* **Build or test failure:** Fix locally; if irreducible, reduce scope **without** violating DoD and update `PHASE_1_SCOPE.lock`.

---

## Conventions & Quality Bars

* **Determinism:** Tests and examples should be reproducible offline.
* **Observability:** Minimal, structured logs around key paths; no noisy spew.
* **Docs:** Module-level docstrings and short README/notes for Phase 1 slice.
* **Security & Privacy:** No secrets committed; provide `.env.example` when needed.
* **Style:** Use linters/formatters if specified; otherwise apply widely-accepted defaults.

---

## How Codex Should Start

1. Read:
   `app_plan/sequence_overall.md` → `app_plan/finalstubs_latest.json` → `app_plan/phases/phase_1.md`
2. Run **Planner**, emit `PHASE_1_SCOPE.lock`.
3. Proceed through roles in order, honoring the Acceptance Checklist.
4. Print, at end of run:

   * Plan summary & chosen scope
   * File tree created/modified
   * Test summary (pass/fail counts)
   * Any follow-ups needed for remaining Phase 1 work

---

This document is the operating manual for Codex’s execution of Phase 1 using `app_plan` and `app_finalstubs`.
