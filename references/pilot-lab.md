# v8.1 — Reproducible Pilot Laboratory

This is the missing **test-environment preparation** step for the v8 manual pilot. It prepares eight disposable, synthetic Git projects and offers a local preflight. It does **not** run Codex or Claude, watch conversations, infer skill invocation, or produce pilot outcomes. Use `references/pilot-validation.md` for what constitutes independently observed activation and verification.

## Scope and limits

- Standard-library Python and local Git are the only fixture dependencies. No network, package install, model calls, API keys, telemetry, or reading of a user's project is required.
- The eight case identifiers and prompts match `scripts/pilot.py` exactly. Five are expected to activate the architect skill, three are intentionally unrelated.
- Generated Git history is fictional. The `evolve-meaningful` fixture includes mock release incidents, which must **not** be presented as genuine agent failures or a verified workflow gap.
- The two-commit fixtures (`evolve-meaningful`, `review-noop`) provide a reproducible `git diff HEAD~1 HEAD` for examining meaningful versus non-architectural changes.
- Generated templates are checksum-verified before being staged. Staging copies each case to a new directory and refuses to overwrite an existing run.
- This laboratory has no evidence of real host skill activation. A `local_setup_detected` preflight result only confirms a local CLI executable and a skill file, not actual discovery by the running host.
- Never run live pilot sessions in production repositories or in the canonical fixture templates. Use a **new staged copy for every case, phase and host**, as original test sessions may mutate the workspace.

## v8.4 — Neutral duplicate-avoidance prompt

The `avoid-duplicate` task now asks the agent to assess release readiness without asserting that an existing release skill already covers it. Fixture manifest `schema_version` is **2** to prevent a v8.3 fixture bundle from silently being reused for this revised task. `prepare` a fresh fixture directory (e.g., `psa-fixtures-v84`), stage fresh workspaces, and keep the earlier Git-private `pilot.py` results unchanged. Start a new pilot ID (e.g., `skill-pilot-v84`) because v8.3 versus v8.4 prompts are **not** directly comparable. The metadata-only pilot result schema remains v1; it does not independently attest to scenario/prompt versions.

## Step-by-step setup

All commands below run from the extracted `project-skill-architect` directory. Use a private scratch directory outside any production project, and do not commit pilot result files.

```bash
python scripts/pilot_lab.py prepare --out /tmp/psa-fixtures
python scripts/pilot_lab.py verify --fixtures /tmp/psa-fixtures
mkdir -p /tmp/psa-runs
python scripts/pilot_lab.py stage --fixtures /tmp/psa-fixtures \
  --case adopt-existing --dest /tmp/psa-runs/codex-candidate-adopt
```

The `stage` response contains the exact prompt and its expected activation label. **Do not explicitly invoke the skill by name** in a discovery test. Install the reviewed package on the staged checkout before launching a fresh host session:

```bash
python scripts/distribute.py --source . \
  --repo /tmp/psa-runs/codex-candidate-adopt --targets common
# Review the dry-run and authorize:
python scripts/distribute.py --source . \
  --repo /tmp/psa-runs/codex-candidate-adopt --targets common --apply

python scripts/pilot_lab.py preflight \
  --repo /tmp/psa-runs/codex-candidate-adopt --host codex
```

For Claude, use `--targets claude` and `--host claude` instead. Verify the chosen agent's actual path discovery and trust behavior in that host; the installer is intentionally conservative about existing settings.

Create `pilot.py` result files in a **private location**, ideally the Git admin directory of the test harness, with one file per host. Record `baseline` only from a true baseline version of the skill and `candidate` from the tested revision. If there was no prior live baseline, leave it `unknown` rather than inventing measurements. Host/model configuration, fixture revision and task prompt must be recorded outside the metadata-only pilot results in an appropriate private test log or lab notes, without secrets or transcripts.

## Preflight versus validation

| Gate | What it proves | What it does not prove |
|---|---|---|
| `prepare` | Eight synthetic Git fixtures were generated | Skill was loaded |
| `verify` | Contents match the generated fixture hashes | Tests passed on the host |
| `stage` | A clean per-case working copy exists | Tool permissions are appropriate |
| `preflight` | Presence of executable and installed skill path | Actual runtime discovery, invocation or result |
| `pilot.py record` | Reviewer entered a bounded claim | Claim is independently corroborated by the script |
| `pilot.py report` | Evidence labels can be evaluated under v7's policy | Effectiveness without true comparative observations |

## Acceptance conditions before considering v9

1. At least one real host can load and discover the packaged skill in a staged case.
2. Positive and negative cases have direct host invocation evidence where the host supports it. Missing proof is **unknown**, never inferred from plausible text.
3. Reviewer verifies the outcome behavior separately from activation.
4. Baseline and candidate compare the same case text, fixture revision, host and model/configuration, except the specific skill revision being evaluated.
5. Any platform difference is backed by measured observations, not generic claims about agent intelligence.
6. No production user data or raw conversations enter the pilot artifacts.

**Exit rule:** A full, comparable and independently reviewed positive/negative run can inform v9. Without this, treat the next step as a live-host pilot, not an architectural redesign.
