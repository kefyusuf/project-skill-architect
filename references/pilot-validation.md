# v8 — Host Pilot Validation Protocol

This protocol turns **real** Codex, Claude Code, Cursor or other agent sessions into a bounded v7 effectiveness dataset. It does not run agents, scrape traces, install hooks, or measure tokens itself. Read [effectiveness.md](effectiveness.md) for metric definitions. The separate `scripts/pilot.py` records only reviewer-entered, privacy-safe labels.

## Why this exists

v6 tool-failure counts cannot prove skill activation, and v7's JSON suite is cumbersome to write manually. The pilot fixes **scenario selection, expected behavior and data entry**. It intentionally does not fabricate missing baselines or observations. A missing baseline leads to `insufficient_evidence` from v7, even when all current runs look correct.

## Preconditions

- Work in a throwaway checkout or synthetic example repository. Do not test write permissions on production repositories.
- Install a reviewed version of `project-skill-architect` according to `README.md` on the selected host. Confirm the host is running the installed version. Never assume the skill loaded because the model produced a plausible response.
- Keep host version, model version, skill revision, agent settings and case prompts **constant** across an A/B comparison. If any change, report it; do not call the phases directly comparable.
- Store the result file in Git-private local storage, such as `$(git rev-parse --git-dir)/project-skill-architect/pilot-codex.json`. Create its parent first. Do not commit individual traces or prompts.
- These prompts are **illustrative**; use identical actual test prompts for baseline and candidate, reviewed for safety. The pilot file stores no prompt text.

## Test scenarios

Run each scenario in a **fresh agent session** with only the intended skill setup. Do not mention the skill name or explicitly force it to activate in this pilot; doing so measures explicit instruction following, not skill discovery. Ask the host to show which skills it activated **if the host supports trustworthy activation evidence**. Absence of a trace is `unknown`, not `skip`.

| Case ID | Expected activation | Example task prompt (in a synthetic repo) | Verification criterion when skill invoked |
|---|---|---|---|
| `bootstrap-project` | invoke | "We are starting a new project. Determine what project skills are actually needed; ask only critical questions. Do not write files yet." | Asks targeted questions, separates skills from ordinary project rules, proposes minimal scope, no edits |
| `adopt-existing` | invoke | "Join this existing example repository. Inspect existing rules and skills before proposing changes; do not edit anything." | Inventories real existing rules/skills, preserves them, identifies gaps without invented facts or edits |
| `evolve-meaningful` | invoke | "We added a new deployment workflow and keep making the same release mistake. Should our skill architecture change? Provide evidence first." | Reviews current instructions/skills and recurrence evidence, recommends at most justified changes |
| `review-noop` | invoke | "Review our skill architecture after a small unrelated code-only PR. Is any skill change actually justified?" | Explicit no-change recommendation when no skill gap is supported |
| `avoid-duplicate` | invoke | "Our team wants an Agent Skill to support release readiness. Examine the existing project rules, skills, and repository evidence. Decide whether a new skill is justified, an existing skill should be revised, or no change is necessary. Explain the evidence. Do not modify files." | Prefers existing skill clarification/repair; does not duplicate unnecessarily |
| `unrelated-bugfix` | skip | "Fix this failing unit test in the example application." | Do not infer non-activation solely from an adequate bug fix |
| `unrelated-writing` | skip | "Proofread this brief paragraph for grammar." | Do not infer non-activation solely from an adequate rewrite |
| `routine-code-change` | skip | "Rename a variable in the example application's test fixture." | Do not infer non-activation solely from a successful edit |

**v8.4 scenario revision:** `avoid-duplicate` no longer states that an existing skill already covers the task; the host must inspect the current contracts to reach that conclusion. This changes the scenario prompt, so prior v8.3 candidate runs (including any manually recorded `unknown`) must remain unchanged and must **not** be treated as comparable v8.4 observations. Run a newly prepared v8.4 fixture set and create a **new** `pilot.py init --pilot-id skill-pilot-v84` result file. The pilot result JSON schema is unchanged and does not embed prompts or automatically enforce suite-version matching. Record exact prompt/fixture/host revisions privately and compare only equivalent runs.

A positive scenario is a **pass** only if the skill was observed to activate AND the reviewer confirmed the stated behavior. For negative scenarios (`expected=skip`), `verification` must remain `unknown`; their correctness is measured by activation, not task quality. Evidence must be direct: a host activation trace, or an explicitly reviewed manual record. **Do not use the agent's self-assertion as independent proof of a hook or skill invocation.** If a host cannot reveal activation, record `unknown` with evidence `none`.

## Commands

From the skill folder (commands shown for Bash; use a platform-appropriate path on Windows):

```bash
mkdir -p .git/project-skill-architect
python scripts/pilot.py init --file .git/project-skill-architect/pilot-codex.json --host codex
python scripts/pilot.py report --file .git/project-skill-architect/pilot-codex.json
```

Run a scenario on the real host. If the reviewer can **directly observe skill activation** and verify the positive case:

```bash
python scripts/pilot.py record \
  --file .git/project-skill-architect/pilot-codex.json \
  --phase candidate --case bootstrap-project \
  --observed invoke --verification pass --evidence reviewed_manual
```

For negative scenarios, use `--observed skip --verification unknown --evidence reviewed_manual` only if there is real evidence for non-invocation. Otherwise use `--observed unknown --verification unknown --evidence none`. Use `--evidence host_trace` **only** when an actual host activation trace was inspected; `--skill-tokens` only when an actual host measurement for *skill tokens specifically* is available. Session input/output tokens are not automatically skill-specific tokens.

To compare pre-change and post-change skills, create a fresh pilot and record **the same eight scenarios** with `--phase baseline` and `--phase candidate` on the same host and controlled configuration. Do not construct historical baseline results from memory. `record` blocks duplicate results and never silently overwrites them. Use a new pilot when you need a fresh trial.

## Reading the report

- `progress`: per-phase number of **observed**, unknown and verified cases. This is completion accounting, **not a quality score**.
- `evaluation.status=insufficient_evidence`: the data does not justify a conclusion, often because baseline or negative-case observations are absent.
- `evaluation.status=review_recommended`: a measured activation mismatch, task verification failure, or baseline regression warrants human review.
- `evaluation.status=no_change`: a limited conclusion for the provided comparable sample; it does not prove general utility, cost savings, statistical significance or production readiness.

**Gates before claiming validated on an actual host:** verify installation, execute all positive and negative scenarios in distinct live sessions, record direct activation evidence, manually verify expected outputs, and publish the exact denominators with model/host/skill revision. Cross-host comparisons must not aggregate token costs. In this package, all host-independent checks are local; live Codex and Claude Code validation must occur in environments where those hosts are available.
