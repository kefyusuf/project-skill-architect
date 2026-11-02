# Changelog

## Unreleased — Windows Codex pilot access

- On Windows, explicitly select the elevated Codex sandbox backend while keeping `--ignore-user-config` and `--sandbox read-only`; other platforms are unchanged.
- Detect stderr policy denials without storing stderr; blocked tool access prevents exit-zero sessions from being reported as completed pilots.
- Count successful Codex command executions separately from unknown skill activation and unverified task outcomes.
- Add regression tests covering platform flags, stderr denials and disposable workspace integrity.

## Unreleased — Python CLI import reliability

- Renamed the project metadata scanner from `scripts/inspect.py` to `scripts/project_inspector.py` so direct script invocation cannot shadow Python's standard-library `inspect` module.
- Updated project instructions, command examples and test imports; added regression tests for standard-library imports from `scripts/` and for the standalone pilot entry point.
- No change to skill decision logic, host invocation permissions, or pilot outcome accounting.

## v8.3 — Bounded host capture and process-level test hardening

- Replaced post-capture stdout size checking with incremental capture and a strict memory budget. Oversized host output stops the child process and produces `unknown`, not an activation assertion.
- Added six tests, including **real OS subprocesses** (Python executables standing in for CLI processes): success, error exit, timeout, oversized stream, privacy boundary and full disposable fixture runner.
- Preserved the opt-in `--execute` requirement, the existing scenario/result formats and all 127 previous tests.
- No real Codex or Claude Code invocation occurred; host activation remains unverified.


## v8.2 — Opt-in real-host CLI pilot bridge

- Added `scripts/pilot_host.py` with read-only preflight/plan and explicitly authorized `run --execute` for one synthetic case in a fresh workspace.
- Codex uses ephemeral JSON read-only execution; Claude Code uses print/plan mode and a narrow tool set. No host binary is bundled.
- Captures only derived process and host skill-tool metadata; no transcripts, prompts, errors, or token totals are saved. Unknown activation remains unknown and positive activation never proves verification.
- Added 17 regression tests covering privacy-safe parsing, negative cases, no side effects in plans, explicit approval, missing host and fake subprocess execution.
- This environment has no Codex or Claude Code CLI: real-host success remains unverified.


## v8.1 — Reproducible live-host pilot preparation

- Added `scripts/pilot_lab.py`: eight deterministic synthetic Git fixtures, safe stage copies, integrity verification and local host setup preflight.
- Added meaningful-versus-noop Git history cases without using private projects or fabricated live agent observations.
- Kept v8 `pilot.py` schema, all prior effectiveness semantics, optional integrations and approval boundaries intact.
- Added ten focused tests and a reproducible Codex/Claude runbook. No real host launch or automatic skill modification.


## v8 — Controlled real-host pilot workflow

- Added a host-independent eight-scenario registry (`scripts/pilot.py`) covering positive and negative meta-skill activation.
- Added reviewer-recorded, privacy-bounded results and a read-only report that delegates metrics to the existing v7 evaluator.
- Kept missing runs explicitly unknown, disallowed result overwrites, and separated candidate-only progress from comparative effectiveness claims.
- Added a real-session protocol with per-case acceptance criteria, version control and evidence limitations.
- No automatic host launch, simulated live results, transcript scraping, new hooks, or skill edits.


## v7 — Evidence-aware, scenario-based effectiveness evaluation

- Added a read-only, privacy-bounded `scripts/effectiveness.py` for reviewed expected/observed skill activation and verification outcomes.
- Added positive/negative trigger metrics, unknown-denominator accounting, optional measured skill token summaries, and matched before/after regression detection.
- Added fail-closed comparison rules (no matching baseline or negative case means insufficient evidence).
- Kept automatic observation, performance claims, skill edits, retirement and hooking out of scope.


## v6 — Optional agent event intake and reviewed v5 handoff

- Added `scripts/agent_events.py` to capture minimal, salted, Git-private tool failure metadata only after explicitly opting into hooks.
- Added Codex structured nonzero Bash-exit handling and Claude Code `PostToolUseFailure` handling; interrupts and ambiguous events are ignored.
- Added deduplication, cross-session requirement, bounded retention, nonblocking lock, and in-memory v5 observation mapping with user-assigned topic.
- Extended guarded host installer with `--collect-failures` (off by default); refuses automatic migration or overwriting existing v4 settings.
- Added privacy/provenance documentation and regression tests; no agent transcript parsing, semantic classification, skill edits, or implicit decisions.


## v5 — Semantic evolution triage without automatic skill creation

- Added `scripts/evolution.py`: read-only, bounded JSON observation triage combined with optional Git/snapshot checkpoints.
- Added distinct-incident recurrence checks, user-confirmed report gating, a single review priority, and grouping of duplicate observations.
- Added optional read-only decision suppression; reviewed evidence is not re-suggested unless its IDs or checkpoint content fingerprints change. No hidden persistent state.
- Added a review protocol, schema examples, and tests for unsafe paths, incomplete evidence, duplicate incidents, suppression, and read-only behavior.
- Explicitly kept automated source semantics, AST parsing, continuous monitoring, LLM use, skill generation, and hook changes out of v5 scope.

## v4 — Opt-in checkpoints for Codex, Claude Code, and GitHub Actions

- Added `scripts/integrate.py` with dry-run by default and explicit `--apply`, refusing to replace any existing host settings/workflow.
- Added `scripts/hook_bridge.py`: bounded, read-only local Git-private snapshot comparison at `SessionStart`, outputting advisory context only for meaningful configuration changes. Missing baseline or malformed input leaves the session unaffected.
- Added `scripts/ci_report.py` and optional GitHub Actions `pull_request` workflow for informational PR summaries with read-only permissions.
- Classified `.codex/hooks.json`, `.claude/settings.json`, and `.claude/settings.local.json` as agent-integration surfaces in checkpoints.
- Added host-integration documentation, new guarded tests, and an end-to-end install/checkpoint smoke test.
- Kept tool calls and skill generation out of hooks and CI. No background daemon and no per-file tool hooks.

## v3 — Evidence-based checkpoint comparison

- Added read-only `checkpoint.py` with Git commit or explicitly approved hash-baseline comparisons.
- Added review-signal and noise-suppression rules.

## v2 — Cross-host skill distribution

- Added inventory, guarded skill synchronization, and host compatibility guidance.
