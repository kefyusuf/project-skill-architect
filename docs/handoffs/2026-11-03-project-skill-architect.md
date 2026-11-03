# Project Skill Architect — Development Handoff

**Checkpoint date:** 2026-11-03  
**Repository:** [kefyusuf/project-skill-architect](https://github.com/kefyusuf/project-skill-architect)  
**Local checkout:** `E:\projects\project-skill-architect`  
**Working branch:** `chore/import-v8.3`  
**Open PR:** [#1](https://github.com/kefyusuf/project-skill-architect/pull/1) → `main`  
**Last implementation commit before this handoff:** `c05f54311e73a714a9f99d284e4ecf58a79b1ffc`  
**CI at checkpoint:** PASS — Ubuntu Python 3.11, Ubuntu Python 3.12, Windows Python 3.13  
**Merge status:** Open and **not merged**

> This is a snapshot of verified work and pending questions. Recheck the branch,
> PR, and CI before making changes. Do not interpret the handoff as authorization
> to merge or enable monitoring.

## 1. Objective and scope

Build a portable, provider- and framework-independent Agent Skill that helps
coding agents **bootstrap**, **adopt**, **audit**, and **evolve** the smallest
effective skill architecture for a repository.

Keep these constraints:

- Evidence-first decisions, explicit unknowns, and no fabricated observations.
- Minimal scope; reuse or revise an existing skill before adding another.
- No agent-triggered edits, hooks, integrations, telemetry, scheduling, or
  production operations without authorization.
- One canonical source of truth; host-specific copies are derived artifacts.
- Do not mistake fixture preparation, plausible agent text, or task completion
  for proof of skill activation or effectiveness.
- No automatic/background execution claims without a verified host trigger.

## 2. Implemented and reviewed capabilities

The branch contains:

- Bootstrap / Adopt / Evolve / Audit workflow guidance.
- Architecture decision rules and cross-host skill location guidance.
- Read-only checkpoint and semantic evolution triage.
- Optional and guarded host integrations; no default installation.
- Redacted agent-event metadata handling.
- Evidence-aware effectiveness evaluation and manual pilot registry.
- Eight reproducible synthetic pilot scenarios and isolated staging.
- Optional real Codex/Claude CLI pilot infrastructure and Windows runner fixes.
- **v8.4:** neutralized `avoid-duplicate` fixture prompt and versioned
  fixture manifest (schema 2), preventing silent reuse of v8.3 fixtures.
- **v8.4:** an opt-in, localhost-only Codex OTLP/HTTP JSON diagnostic probe.

Recent source paths:

- `scripts/codex_otel_probe.py`
- `tests/test_codex_otel_probe.py`
- `references/pilot-validation.md` (includes PowerShell instructions)
- `scripts/pilot_lab.py`
- `scripts/pilot.py`
- `references/pilot-lab.md`
- `CHANGELOG.md`

The diagnostic counts `codex.skill_invocation` events in memory; it never
stores raw HTTP payloads. It binds to `127.0.0.1` and runs only when explicitly
launched. A missing event is **unknown**, never proof of a `skip`. Other
telemetry events may still contain sensitive data, so this diagnostic is for
**disposable synthetic fixtures only**.

## 3. Pilot evidence and interpretation

### v8.3 pilot

Eight scenarios were executed in real Codex CLI sessions using synthetic
workspaces. Results were entered by manual review:

| Scenario | Expected | Observed / verification |
| --- | --- | --- |
| `bootstrap-project` | invoke | invoke / pass |
| `adopt-existing` | invoke | invoke / pass |
| `evolve-meaningful` | invoke | invoke / pass |
| `review-noop` | invoke | invoke / pass |
| `avoid-duplicate` | invoke | unknown / unknown |
| `unrelated-bugfix` | skip | unknown / unknown |
| `unrelated-writing` | skip | unknown / unknown |
| `routine-code-change` | skip | unknown / unknown |

The four confirmed positives involved direct skill-file inspection and
independent review of the expected decision. No explicit host activation trace,
controlled baseline, reliable negative-case non-invocation evidence, or
skill-specific token measurements were available.

**Evaluator status:** `insufficient_evidence`.

Git-private result file:
`.git/project-skill-architect/pilot-codex.json`

### v8.4 pilot

The `avoid-duplicate` scenario was revised to avoid stating in the prompt that
the existing release skill already covers the requested workflow. In a fresh
real Codex session, the agent read both the Project Skill Architect definition
and the existing `release-check` definition, inspected the synthetic
repository, and recommended reusing / narrowly clarifying the existing skill
instead of adding a duplicate. No project file was edited.

**Recorded candidate results:** 1 verified, 7 unknown.  
**Baseline results:** 8 unknown.  
**Evaluator status:** `insufficient_evidence`.

Git-private result file:
`.git/project-skill-architect/pilot-codex-v84.json`

Do **not** overwrite either result file, merge the v8.3 and v8.4 prompt
versions as equivalent observations, or infer a `skip` from no recorded event.

## 4. Exact next checkpoint

The next narrowly scoped task is **Codex skill-activation telemetry
feasibility**, not a new feature or infrastructure redesign.

1. Refresh the current branch and confirm PR status:
   `git pull --ff-only origin chore/import-v8.3`.
2. Run the probe unit tests:
   `python -m unittest discover -s tests -p "test_codex_otel_probe.py" -v`.
3. In terminal 1, start the disposable receiver:
   `python scripts/codex_otel_probe.py --port 43181`.
4. In terminal 2, follow the exact fresh-fixture and CLI-only OTLP setup in
   [references/pilot-validation.md](../../references/pilot-validation.md).
5. Stop the receiver after Codex exits; review the `SUMMARY` counters and
   separately inspect Codex task behavior.
6. Confirm whether the installed CLI actually emits and delivers a
   `codex.skill_invocation` event. Even if it does, an absent event does
   **not** prove that a skill was skipped.
7. Record any verified new measurements in a *separate* pilot session with
   accurate configuration metadata, without overwriting prior results.

No real Codex-to-receiver event delivery has been verified yet. The probe's
local tests and CI demonstrate implementation behavior, **not** runtime
telemetry delivery or the skill's effectiveness.

## 5. Known issues and unresolved evidence

- Codex repeatedly attempted to read a nonexistent
  `references/extension-lifecycle.md`; the origin is not established.
- Combined PowerShell commands sometimes returned success despite an earlier
  `Get-Content` failure; check each command independently.
- A search tool's exit code 1 may mean *no matches* rather than a runtime
  failure; interpret in context.
- User-global skill installations may confound nominally isolated Codex
  sessions, even with `--ignore-user-config`.
- The standard `codex exec --json` stream does not furnish reliable
  non-activation evidence.
- A controlled baseline/candidate comparison has not been performed.
- No proof of general utility, token savings, or production readiness exists.

These are investigation findings, **not** blanket authorization to build a
collector, dashboard, database, persistent daemon, or cross-host framework.

## 6. Working and approval rules

- Use TDD: RED → smallest GREEN → refactor and verify.
- Follow repository conventions; documentation and code comments in English,
  discussion with the user in Turkish.
- Preserve application code, unrelated project files, permissions and
  previously reviewed decisions.
- Keep evidence and tests inspectable; never manufacture observations to turn
  an `unknown` into a pass.
- Do not add AI/assistant/tool co-author or attribution lines.
- Use GitHub as the canonical development location; do not require separate
  source-code downloads.
- Keep changes on the existing reviewed PR branch unless an independently
  justified branch is needed.
- Review actual changes and CI gates before any merge.
- **Do not merge PR #1 without explicit authorization.**

## 7. Resume instruction

Continue from this handoff, beginning with a fresh check of PR #1, its head
commit and CI. Focus only on the safe, opt-in Codex OTLP diagnostic and its
real-host evidence limitations. Preserve all Git-private pilot records.
Do not expand project scope or merge without authorization.
