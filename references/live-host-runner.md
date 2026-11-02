# v8.3 — Explicit real-host pilot runner (bounded capture)

This is the first **opt-in attempt to execute a real installed coding-agent CLI** in this project. It builds on v8.1 fixtures and v8 `pilot.py`. It **does not** install a CLI, authenticate, change a real application repository, infer task correctness, or mark pilot cases successful.

## Architecture and gates

1. `pilot_lab.py prepare` generates eight entirely synthetic, checksum-protected Git fixture repositories.
2. `pilot_host.py plan` **never writes** and reports whether a host CLI is discoverable.
3. Only `pilot_host.py run ... --execute` creates a **new disposable directory** and installs the checked skill into it; it refuses pre-existing destination directories, templates, and locations inside its canonical skill source.
4. It launches the locally installed `codex` or `claude` command for **one scenario**, using an existing user authentication context. This can incur model usage or subscription/API costs. Nothing runs automatically. Use one new directory per case and per version; do not use real projects.
5. Host output is captured in memory, parsed for bounded metadata, then discarded. The runner does not save prompts, raw JSONL, agent messages, user files, stderr, token estimates or transcripts into pilot results.
6. A reviewer separately decides whether the skill was discovered and whether its behavior was correct. Recording is manual in `pilot.py`, never done by `pilot_host.py`.

## Platform safeguards and limitations

- Codex: `codex exec --json --ephemeral --ignore-user-config --sandbox read-only` (with `-c 'windows.sandbox="elevated"'` on Windows). The Windows override selects the CLI sandbox backend; it does not change the `read-only` permission. An initial Windows sandbox setup may request system approval. Don't proceed if a security prompt is unexpected. Codex CLI JSON events document turn completion, not a reliable universal skill-activation event. Therefore `observed=unknown` remains the default. It is **not** safe to interpret a successful process exit as the skill being activated. Existing project rules still apply.
- Claude Code: `claude -p --output-format stream-json --verbose --no-session-persistence --permission-mode plan --tools Read,Glob,Grep,Skill --disallowedTools mcp__* --max-turns 6`. When the streamed assistant tool call explicitly invokes `Skill` with the **exact** `project-skill-architect` name, the runner records a positive *tool-use signal*. If this implementation of Claude Code doesn't expose such an event, the result is `unknown`. A tool signal does **not** mean the skill's steps succeeded; verification remains `unknown` until reviewed.
- Both: a nonexistent CLI fails before staging the workspace; a timeout or malformed/unconfirmed stream does not count as success. The runner cannot force a local host to ignore all external machine settings, non-CLI integrations, authentication caches, provider calls or global hooks. Do not test untrusted skills or run on a machine whose host configuration is unsafe.
- Host stdout is consumed **incrementally** with a 12 MiB in-memory cap (plus at most one 64 KiB chunk). If this cap is exceeded the child process is terminated and the result is not graded. No raw output is saved by this runner. The OS, CLI, third-party hooks or child processes may still log independently. Session/tool processes may persist their own internal state despite CLI flags; inspect platform privacy settings.
- No claim of a complete hermetic sandbox is made. The runner is intended only for synthetic fixtures and human-reviewed testing. `workspace_unchanged=false` indicates that the staged working copy changed and needs investigation, not proof of misbehavior.

## Usage: Linux/macOS

Run from the unpacked `project-skill-architect` directory:

```bash
mkdir -p /tmp/psa-runs
python scripts/pilot_lab.py prepare --out /tmp/psa-fixtures

# Preview: NO host invocation or writes
python scripts/pilot_host.py plan --fixtures /tmp/psa-fixtures \
  --case adopt-existing --host codex --dest /tmp/psa-runs/codex-adopt

# Explicitly launch on a disposable workspace. May consume paid host usage.
python scripts/pilot_host.py run --fixtures /tmp/psa-fixtures \
  --case adopt-existing --host codex --dest /tmp/psa-runs/codex-adopt --execute
```

## Windows PowerShell

```powershell
$fixtures = Join-Path $env:TEMP 'psa-fixtures'
$runs = Join-Path $env:TEMP 'psa-runs'
New-Item -ItemType Directory -Force $runs | Out-Null
python scripts/pilot_lab.py prepare --out $fixtures
python scripts/pilot_host.py plan --fixtures $fixtures --case adopt-existing --host claude --dest "$runs\claude-adopt"
python scripts/pilot_host.py run --fixtures $fixtures --case adopt-existing --host claude --dest "$runs\claude-adopt" --execute
```

Use a fresh `$fixtures` name if you already prepared the fixtures; the tool intentionally refuses overwriting them.

On Windows, Codex uses the same `read-only` permissions plus an explicit Windows sandbox backend when user config is ignored. This fixes the observed `blocked by policy` shell-tool failure on Codex CLI 0.166.0. A command execution only confirms a tool ran; it does not prove the skill activated.

## Reading results

```json
{
  "process_status": "completed",
  "skill_activation": "unknown",
  "observed": "unknown",
  "verification": "unknown",
  "pilot_result_written": false
}
```

This means the *host process* completed according to the host's structured stream; **nothing was concluded about the skill**. The optional `tool_access` field is `command_executed` only when a successful Codex command event is observed, `unverified` when none is observed, or `blocked` when stderr contains a policy denial. `blocked` forces `process_status=failed_or_unconfirmed` even if the CLI exits 0. No command event, even a successful file read, proves that a skill activated. If a supported named Claude `Skill` tool call is visible, `skill_activation` may read `host_tool_signal` and `observed` may read `invoke`. Absence of that call is **never** recorded as `skip`.

After inspecting genuine host evidence and the resulting behavior, use the existing private `scripts/pilot.py init` / `record` / `report` workflow. Use `reviewed_manual` if there is a human-reviewed observation but no explicit host activation event; only record `host_trace` if the trace actually verifies invocation. Leave unknown cases unrecorded, including the unobservable negative cases. Token totals for the *entire* CLI session are not skill-specific token costs; keep `skill_tokens=null`.

## Reproducibility

For a meaningful baseline/candidate comparison, preserve host, model/configuration, original case, fixture version and installed skill revision. Don't label first-time candidate-only observations as a comparative improvement. Local tests mock host process results and are **not real Codex or Claude validation**.

## v8.3 reliability change and evidence distinctions

- `capture_bounded()` starts an OS child process, drains its stdout in bounded chunks, scans stderr for a policy-denial marker without retaining stderr, and kills the CLI process after a timeout or an output-budget breach. A timeout or overflow is always `unknown` for skill activation and task verification.
- The additional tests launch **real operating-system subprocesses** using the Python executable. They validate runner plumbing, not agent reasoning or skill discovery. The existing host-mock tests remain in place.
- This runner **does not guarantee termination of grandchildren** created by coding agent CLIs, containment of host-global hooks, or protection from the host CLI's own logging. Run only on a machine and host configuration you trust.
- Do not treat a successful process exit, a final answer containing the skill name, or a missing invocation signal as an automatic grade. Use `pilot.py record` only after independent review and preserve unknown cases.
- Real pilot evidence still needs one genuine Codex session and one genuine Claude Code session using the same synthetic scenarios. A repository is optional for this local step; it becomes useful for collaborative review and preserving versioned, **sanitized** test assets.
