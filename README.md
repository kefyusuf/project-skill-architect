# Project Skill Architect

A portable Agent Skills meta-skill for **bootstrap**, **adopt**, **evolve**, and **audit** workflows, with opt-in evidence-driven checkpoint comparison, guarded host integrations, and read-only semantic evolution triage, and optional redacted agent-event collection. It can discover an existing project's instruction and skill layout, ask selective questions, recommend the smallest justified architecture, and help create or safely revise skills when authorized.

**This is a skill, not a background daemon.** It runs when invoked. v4 can optionally install narrowly scoped `SessionStart` hooks and a GitHub pull-request check, with explicit user authorization. Neither integration automatically creates or modifies skills.

## Install or synchronize

The recommended cross-agent authoring location is `.agents/skills/` for hosts that support it. Claude Code normally needs `.claude/skills/`. The script is a guarded convenience tool; run preview first and inspect its output.

```bash
# Read-only preview (no writes):
python scripts/distribute.py --source . --repo /path/to/project --targets common,claude

# Explicitly install to those locations:
python scripts/distribute.py --source . --repo /path/to/project --targets common,claude --apply

# Also include VS Code Copilot's native location if needed:
python scripts/distribute.py --source . --repo /path/to/project --targets common,claude,copilot --apply
```

A synchronized copy is a **derived installation**, not an independently editable definition. The script refuses to overwrite unmanaged targets or managed targets that were modified after the last sync. It also avoids overwriting canonical source folders.

For ongoing work on project-specific skills authored in `.agents/skills/<skill-name>`, run `--source /path/to/project/.agents/skills/<skill-name> --targets claude --apply` after approving a change. Other host support and alternate directories are documented in `references/platforms.md`.

## Typical requests

- **Bootstrap**: "We're starting a new project. Ask only what you need to propose a minimal skill structure. Do not choose a framework for me."
- **Adopt**: "Inspect this existing repository, reconstruct current agent rules, tests and skills, and show what should be preserved or changed. No edits yet."
- **Evolve**: "We introduced a new service and deployment mistakes recur. Re-evaluate the existing skill architecture and propose only the highest-value change."
- **Audit**: "Find duplicated triggers or conflicting skills across Codex, Claude Code and OpenCode. Report without editing."

You can optionally place a short checkpoint instruction into an existing agent instruction file with user approval; see `assets/checkpoint-instruction.md`. This can improve discoverability **during a live session**, but is not an unattended monitoring service.

## Read-only inspection

```bash
python scripts/project_inspector.py --repo /path/to/project
```

The scanner inventories common files and skill frontmatter, does not read application source or secret files, and does not write to the repository. It deliberately makes no claims about project correctness or full discovery in monorepos.

## Important checkpoints (v3)

The new `scripts/checkpoint.py` reads bounded allowlisted repository metadata and compares either a Git base revision or an explicitly approved hash snapshot. It **does not launch an agent, create a skill, edit the repo, configure hooks, or run in the background**. The human/agent review determines whether existing instructions or skills are inadequate; `no change` is a valid decision.

```bash
# Pull-request/release-like comparison, committed changes only (read-only):
python scripts/checkpoint.py --repo /path/to/project --since-ref origin/main --event pr

# First adoption: explicitly save a baseline outside the tracked project:
python scripts/checkpoint.py --repo /path/to/project --save-baseline /path/to/local/checkpoint.json

# Later: read-only working-tree comparison:
python scripts/checkpoint.py --repo /path/to/project --baseline /path/to/local/checkpoint.json --event manual

# Only after completing the review: explicitly acknowledge the new baseline:
python scripts/checkpoint.py --repo /path/to/project --save-baseline /path/to/local/checkpoint.json --replace-baseline
```

When no base revision/snapshot is supplied, a generic check returns `insufficient_evidence`, not a misleading `no change`. Explicit architectural/workflow incidents can produce a review signal even without a saved baseline, clearly marked as declared rather than automatically verified.

To make checkpoint evaluation visible *during active agent work*, propose the optional snippet in `assets/checkpoint-instruction.md` for the project's existing, approved `AGENTS.md`/`CLAUDE.md`. Never install it, a host hook, or a CI workflow silently. See `references/checkpoints.md` for evidence gates, noise suppression, security boundaries and host-specific limitations.

## Optional Codex, Claude Code, and GitHub checkpoints (v4)

The optional integration script **does not change existing settings**. It creates only missing configs after a reviewed `--apply`. Install the canonical skill first, then preview:

```bash
python .agents/skills/project-skill-architect/scripts/integrate.py \
  --repo /path/to/project --hosts codex,claude,github

# After examining the generated settings and accepting hook execution:
python .agents/skills/project-skill-architect/scripts/integrate.py \
  --repo /path/to/project --hosts codex,claude,github --apply
```

On Codex and Claude Code, the `SessionStart` hook compares allowlisted local project surfaces against an **explicitly approved Git-private baseline**. Without a baseline it emits no suggestions, and no baseline is ever written by the hook. To enable local comparisons in a normal Git repo, from the **project root**:

```bash
python .agents/skills/project-skill-architect/scripts/checkpoint.py \
  --repo . --save-baseline .git/project-skill-architect/baseline.json
```

For Git worktrees, obtain the baseline path using `git rev-parse --git-path project-skill-architect/baseline.json` instead of assuming `.git` is a directory. Record/re-record a baseline only after a deliberate human review. GitHub PR checks compare the base commit to the current checked-out revision and require no local baseline; they emit a step summary but do not fail the PR simply because skill-related configuration changed.

**Important:** The generated host hook commands use absolute local paths and may need reinstallation after moving the checkout or changing Python. Existing Codex/Claude settings cannot be merged automatically; manually integrate after comparing them. Read [references/integrations.md](references/integrations.md) for Windows limitations, trust prompts, GitHub security boundaries, and the no-overwrite contract.

## Structured project evolution triage (v5)

v5 adds `scripts/evolution.py`. It correlates **typed, reported** changes with any optional v4 checkpoint signal. It does **not** parse application code or independently detect that a new microservice/workflow exists. Its `review_recommended` output means that the active agent should check existing project rules/skills before proposing at most one minimal change. No file edits or agent invocations occur.

```bash
# Sample reported repeated-failure input, read-only evaluation:
python scripts/evolution.py --repo /path/to/project \
  --observations assets/observations.example.json

# Combine declared observations with a Git PR checkpoint:
python scripts/evolution.py --repo /path/to/project \
  --since-ref origin/main --event pr \
  --observations /path/to/observations.json

# Optional manually recorded decisions suppress already-reviewed evidence:
python scripts/evolution.py --repo /path/to/project \
  --observations assets/observations.example.json \
  --decisions assets/decisions.example.json
```

See [references/semantic-evolution.md](references/semantic-evolution.md) for the JSON contracts, the distinctions between reported and verified evidence, recurrence thresholds, and the **manual** decision history. `assets/*.example.json` are demonstrations, not repository-specific truths. Do not install watchers, per-tool hooks, schedulers, or new skill files as a consequence of this triage without the user's separate approval.

## Opt-in agent-aware events (v6)

v6 adds `scripts/agent_events.py`, a **privacy-minimizing, local-only** collector and a reviewed handoff into v5. On supported hosts, it can record coarse tool-failure metadata when the user explicitly installs the **additional** hook. **No raw commands, prompts, errors, transcripts, or tool outputs are saved.** Tool-failure statistics are *not* proof of an architectural or skill gap.

```bash
# From project root, after installing the canonical skill, preview new-host setup:
python .agents/skills/project-skill-architect/scripts/integrate.py \
  --repo . --hosts codex,claude --collect-failures

# If authorized, enable collection only in a checkout with NO existing host config:
python .agents/skills/project-skill-architect/scripts/integrate.py \
  --repo . --hosts codex,claude --collect-failures --apply

# Read-only inventory of anonymized event IDs and category counts:
python .agents/skills/project-skill-architect/scripts/agent_events.py inspect --repo .

# Only after separately confirming two events belong to the same workflow:
python .agents/skills/project-skill-architect/scripts/agent_events.py evaluate \
  --repo . --topic deployment-workflow --event-ids <id-1> <id-2>
```

Already-installed v4 hooks **cannot be auto-merged**; the installer deliberately blocks and requires a human-reviewed edit. The hook collector is best-effort and cannot see every failure; Codex events without a structured nonzero shell exit are intentionally ignored. To preserve privacy, events are saved only under the local Git administration directory and capped at 200; no background service or remote analytics are introduced. See [references/agent-aware.md](references/agent-aware.md) for its data contract, retention, security risks, and manual review protocol.

## Quality checks

```bash
python scripts/validate.py .
python -m unittest discover -s tests -v
```

The included validator is lightweight. If available, use the official Agent Skills reference validator for stronger metadata checks and test trigger behavior inside the actual target agent. Tests in this package exercise filesystem tools and safeguards, not automatic skill activation in Codex, Claude Code, or other products.

## Files

- `SKILL.md`: operating contract and four modes
- `references/discovery.md`: adaptive questions and brownfield discovery
- `references/architecture-rules.md`: skill vs instruction vs tooling classification
- `references/lifecycle.md`: evidence thresholds and evolution proposals
- `references/checkpoints.md`: checkpoint signal interpretation and approved baseline protocol
- `references/platforms.md`: verified paths and compatibility guidance
- `assets/skill-template.md`: optional content guide for generated skills
- `assets/architecture-log-template.md`: optional project decision record
- `assets/checkpoint-instruction.md`: optional short text for host instruction files
- `scripts/project_inspector.py`: read-only bounded project inventory
- `scripts/checkpoint.py`: read-only compare and opt-in baseline recording
- `scripts/distribute.py`: dry-run-first, guarded distribution
- `scripts/validate.py`: dependency-free structural validation
- `scripts/integrate.py`: guarded opt-in Codex/Claude/GitHub integration generator
- `scripts/hook_bridge.py`: read-only, non-blocking SessionStart context bridge
- `scripts/ci_report.py`: informational GitHub PR step-summary renderer
- `references/integrations.md`: host setup/trust/security and baseline protocol
- `tests/test_tools.py`: unit tests for safe installation and validation
- `tests/test_checkpoint.py`: signal detection, authority boundaries, baseline and Git checks

- `tests/test_integration.py`: integration configuration, baseline gating, hook output and PR workflow safeguards

- `scripts/evolution.py`: read-only, deterministic typed-observation and checkpoint triage (v5)
- `references/semantic-evolution.md`: evidence contract, reviewer workflow, and decision history (v5)
- `assets/observations.example.json`, `assets/decisions.example.json`: non-project-specific example inputs
- `tests/test_evolution.py`: v5 evidence-gating, deduplication, and non-mutation tests

## Reproducible pilot environment (v8.1)

`pilot.py` still requires **actual reviewer observations**. The new `scripts/pilot_lab.py` supplies isolated, deterministic synthetic Git fixtures for the same eight scenarios. It never launches a coding agent or invents activation results.

```bash
python scripts/pilot_lab.py prepare --out /tmp/psa-fixtures
python scripts/pilot_lab.py verify --fixtures /tmp/psa-fixtures
mkdir -p /tmp/psa-runs
python scripts/pilot_lab.py stage --fixtures /tmp/psa-fixtures \
  --case adopt-existing --dest /tmp/psa-runs/codex-candidate-adopt

# Dry-run install, then separately review and authorize --apply:
python scripts/distribute.py --source . --repo /tmp/psa-runs/codex-candidate-adopt --targets common
python scripts/distribute.py --source . --repo /tmp/psa-runs/codex-candidate-adopt --targets common --apply
python scripts/pilot_lab.py preflight --repo /tmp/psa-runs/codex-candidate-adopt --host codex
```

Use `--targets claude` / `--host claude` for Claude Code. For each host, phase, and scenario, stage a **separate** disposable workspace. A preflight with `local_setup_detected` proves neither skill discovery nor invocation. Record only true observations using `scripts/pilot.py`; never mistake synthetic fixtures for real agent test results. Full procedure: [references/pilot-lab.md](references/pilot-lab.md).

## Real-host pilot protocol (v8)

The optional `scripts/pilot.py` creates a **fixed eight-scenario** registry to help reviewers test the installed meta-skill in actual Codex, Claude Code and other hosts. It is a manual evidence capture and v7 analysis frontend, **not** a host emulator or a hidden transcript collector. There are five positive scenarios (project bootstrap, adoption, evolution, no-change review and duplicate prevention) and three negative scenarios (unrelated tasks). All begin as `unknown`.

For a normal Git repository, store the pilot inside its Git-private directory, not in tracked project files. The following simple `.git/` example is for a non-worktree checkout:

```bash
mkdir -p .git/project-skill-architect
python scripts/pilot.py init --file .git/project-skill-architect/pilot-codex.json --host codex
python scripts/pilot.py report --file .git/project-skill-architect/pilot-codex.json

# Run a real session on the selected host, then record only independently reviewed results:
python scripts/pilot.py record --file .git/project-skill-architect/pilot-codex.json \
  --phase candidate --case bootstrap-project \
  --observed invoke --verification pass --evidence reviewed_manual

python scripts/pilot.py report --file .git/project-skill-architect/pilot-codex.json
```

Use the **same eight cases** in baseline and candidate sessions only when both were truly run. The evaluator still returns `insufficient_evidence` for a candidate-only pilot, even if recorded results look good; the progress report separately shows what was observed. Review `references/pilot-validation.md` for prompts, evidence rules, actual-host preconditions, and per-case acceptance criteria. No live host is bundled with this package.

## Skill effectiveness evaluation (v7)

The optional `scripts/effectiveness.py` **does not** automatically observe skill use. It assesses explicitly provided, reviewed cases with baseline/candidate phases, positive/negative invocation expectations, observed activation, independently verified outcomes and optional **host-measured** skill-token counts.

```bash
# Synthetic example for understanding the schema; NOT evidence of real Codex success:
python scripts/effectiveness.py evaluate --suite assets/effectiveness-suite.example.json

# Actual audit: build a de-identified scenario suite from reviewed host execution evidence:
python scripts/effectiveness.py evaluate --suite /path/to/reviewed-scenarios.json
```

Output statuses are `review_recommended`, `insufficient_evidence`, and `no_change` (only for comparable, observed positive and negative cases without detected issues). `no_change` means no issue in the supplied sample, not proven universal usefulness. There is no auto-trigger, no automatic context/token accounting, no permission to change skills, and no telemetry upload. This separate path must not derive success scores from the v6 failure ledger. Read [references/effectiveness.md](references/effectiveness.md) for the strict JSON contract, measurement limitations and adoption rules.

## Optional real CLI pilot bridge (v8.2)

This package includes `scripts/pilot_host.py` to **actually launch** a local Codex or Claude Code CLI on one fresh **synthetic** fixture, only with explicit `run ... --execute`. The default `plan` action is read-only. No host CLI is bundled; authentication and any usage cost are controlled by the user's own installation. This tool does **not** grade skills or write pilot results.

```bash
# After creating fixtures with pilot_lab.py prepare and an empty runs parent:
python scripts/pilot_host.py plan --fixtures /tmp/psa-fixtures \
  --host codex --case adopt-existing --dest /tmp/psa-runs/codex-adopt

# Explicit execution (may use paid model credits):
python scripts/pilot_host.py run --fixtures /tmp/psa-fixtures \
  --host codex --case adopt-existing --dest /tmp/psa-runs/codex-adopt --execute
```

The output distinguishes CLI completion from **verified skill invocation** and **verified task success**. The absence of a named host activation event remains `unknown`; plain text from an agent claiming it used a skill is not accepted as an activation trace. Review [references/live-host-runner.md](references/live-host-runner.md) for Codex/Claude restrictions, PowerShell commands, privacy tradeoffs and how to turn independently reviewed observations into v8 pilot reports. Do not run this against application repositories.

## Bounded pilot runner hardening (v8.3)

`pilot_host.py run --execute` now consumes host stdout incrementally, imposing a hard **12 MiB retained-output cap** instead of checking size only after `subprocess.run` has already captured it. It terminates the main host process on output overflow or timeout. Such results remain **unknown**, not failed skill behavior. The agent's own logging or descendant subprocesses are outside this guarantee. No changes to the pilot result schema or the original eight scenarios were made.

v8.3 adds independent tests that launch **real Python OS subprocesses** to exercise success, failure, timeout, and output-overflow paths. This validates process handling, **not** real Codex/Claude behavior; neither executable is available in the development environment used for this release.

```bash
python -m unittest discover -s tests -q
python scripts/validate.py .
python scripts/pilot_host.py --help
```

Next validation gate: run the existing `pilot_host.py plan` and `run --execute` protocol on a trusted machine with locally installed, authenticated Codex and Claude Code CLIs. The run can incur model usage. Keep all pilot observations local until reviewed and sanitized. A GitHub repository is **not required yet** for this test and should not be created merely to publish synthetic results.
