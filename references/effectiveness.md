# v7 — Skill effectiveness evaluation (optional, read-only)

## Purpose and boundary

This is an **evaluation harness**, not skill telemetry. Unlike v6's opt-in, coarse **tool-failure** collector, it never assumes a failed command proves a skill defect or that an invocation happened. Explicit expected/observed scenario labels must be supplied from independently reviewed evidence. It never reads agent transcripts, sends data to external services, opens project files, modifies any skills, or changes the approved decision history. It does not automatically activate during coding sessions.

Evaluate only when a user asks, at an approved checkpoint, or after a meaningful skill modification. Avoid evaluating every ordinary edit. Follow [lifecycle.md](lifecycle.md) and existing project instructions; on brownfield projects **Adopt before evaluating**.

## Scenario suite

The file `assets/effectiveness-suite.example.json` contains synthetic, non-user data. Do not treat it as actual testing evidence. Use `scripts/effectiveness.py evaluate --suite <reviewed-suite.json>` to generate a JSON report. This tool has **no `--apply` mode**.

Schema is intentionally strict and bounded: root object contains only `schema_version` (1), `suite_id` (short slug), and `runs` (max 500). Each run requires **exactly**:

| Field | Meaning |
|---|---|
| `case_id` | Non-sensitive stable scenario ID. Same ID across baseline/candidate means same scenario and environment by reviewer assertion. |
| `skill` | Non-sensitive skill slug (not the content of SKILL.md). |
| `host` | `codex`, `claude`, `cursor`, `gemini`, `opencode`, or `other`. |
| `phase` | `baseline` or `candidate` (before/after a proposed or implemented skill revision). |
| `expected` | `invoke` or `skip`: reviewed expected activation for the task. |
| `observed` | `invoke`, `skip`, or `unknown`: what the host actually did, not what the user hoped. |
| `verification` | `pass`, `fail`, `unknown`: separately checked result **only** for expected + observed invocation. |
| `evidence` | `host_trace`, `reviewed_manual`, or `none`; `none` only for `observed=unknown`. |
| `skill_tokens` | `null` unless the **host measured actual skill-specific loaded token count** on this invocation. Only allowed for `host_trace` and `observed=invoke`. |

All string identifiers are short allowlisted slugs. No free text, prompts, commands, paths, errors, transcript excerpts, email addresses, or unreviewed log blobs are allowed. The input parser limits file size to 1 MiB. Do not commit project-specific evaluation inputs unless their publication has been separately reviewed. The CLI stdout reports synthetic or supplied metrics only.

## How to construct a test suite

1. Choose a **single skill change**. Hold the host, tool configuration, task definition and expected behavior as steady as feasible for before/after comparisons. Keep case IDs stable, but never copy observed values between phases without new evidence.
2. Define at least one positive (`expected=invoke`) and one negative (`expected=skip`) scenario for each skill/host under test; include ambiguous cases with `observed=unknown` until reviewed. Expected labels are a **human acceptance contract**, not automatically extracted from user conversations.
3. Execute the tasks in an actual host if possible. Review host traces or independently reviewed manual notes to label observed activation. Confirm required quality checks separately; do not infer verification from successful skill loading.
4. Enter measured token counts only if explicitly reported for that skill invocation by the host. The script never estimates token count using file bytes, characters, or heuristics.
5. Run the evaluator. Keep raw traces out of the evaluation file. Compare only paired `(host, skill, case_id)` with unchanged expected label. Different models, host versions, settings or fixtures may invalidate comparison; document that **outside** the suite if necessary.

## Metric interpretation

- **Activation precision** = true positives / (true positives + false positives). Missing denominator gives `null`, **not zero**.
- **Activation recall** = true positives / (true positives + false negatives). No known expected positive gives `null`.
- **Verification success** = independently verified passes / (passes + fails) for *correctly invoked* positive scenarios. Unknown verification is separately counted and excluded.
- **Context** = min/max/mean of explicitly measured `skill_tokens` only. A missing measurement is not zero. Do not compare across heterogeneous hosts, harnesses, different content, or models as if interchangeable. These values are not total session token costs.
- **Paired regressions** report baseline correct -> candidate incorrect activation and baseline verified pass -> candidate verified fail. The result includes case IDs with host and skill to avoid collisions.

All rates describe **the supplied cases only**; they are not representative of production unless the scenario selection and sampling justify that conclusion. v6 collector records coarse failures but has no success-denominator or skill-use proof and must **not** be used to fill these fields automatically.

## Status and decision gates

- `review_recommended`: any evidenced candidate wrong trigger, verified failure, or detected paired regression. Review existing skill, instructions, expected labels, environment and acceptance checks **before** proposing changes. Failure does not authorize removal or a new skill.
- `insufficient_evidence`: missing/unknown observation, no matched baseline, missing negative cases, or unmatched candidate cases. Collect evidence instead of declaring success.
- `no_change`: both positive and negative candidate scenarios are observed, all candidate cases have comparable baseline cases, and there is no observed failure or paired regression. It means **no issue detected in this suite**, not proof of universal effectiveness.

For a normal development checkpoint, report at most **one** prioritized review suggestion. Prefer repair, merging or clarifying an existing skill over adding another. **Any skill edits or hook configuration still require separate authorization.** Never auto-retire a skill based on these metrics.

## How to measure actual usefulness later

If the user wants statistically meaningful claims, repeat cases across multiple runs, compare quality and total host-reported session tokens under controlled conditions, and distinguish skill benefit from model/host/temperature changes. These are **future experiments**, not capabilities delivered by this script. The v7 CLI supports paired cases, but not repeated trials of the same case+phase; avoid claiming confidence intervals or cost reductions from one paired suite.

## Sources

- OpenAI, *Testing Agent Skills Systematically with Evals*: https://developers.openai.com/blog/eval-skills
- OpenAI, *Build skills*: https://learn.chatgpt.com/docs/build-skills
- Anthropic, *Agent Skills overview*: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
