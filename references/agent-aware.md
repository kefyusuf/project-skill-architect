# v6 — Agent-aware, privacy-minimizing event intake

This reference describes an **optional**, explicitly enabled, local-only evidence collector. It does **not** continuously inspect transcripts, analyze source code, assign root cause, propose new skills automatically, or alter any skill/decision.

## Host sources and trust limits

| Host | Captured event | Minimum condition | What is discarded |
|---|---|---|---|
| Claude Code | `PostToolUseFailure` | Not an interruption; opaque `session_id` and `tool_use_id` | Tool input, output, error text, prompts, transcript, filenames |
| Codex | `PostToolUse` for `Bash` | Explicit integer `tool_response.exit_code != 0` and opaque IDs | Command, stdout/stderr, remaining tool response, prompts |
| Other Agent Skills hosts | Manual typed v5 observations | User/agent supplies bounded evidence | No invented native hooks |

The Codex response representation varies by tool/runtime. **If a structured exit code is unavailable, collection skips that event** rather than treating an ambiguous result as failure. Some errors will never be observed. Hooks are best-effort, not a complete security or observability boundary.

## Local privacy and retention

- The code stores only `{id, session, host, category, captured_at}` per event. The ID/session are salted SHA-256 digests of ephemeral hook identifiers. The salt is local to this project.
- State is written **only after an explicit, opt-in hook has been installed and triggered**, and only under the repository's Git-private administrative directory: `git rev-parse --absolute-git-dir` plus `project-skill-architect/events.json`. This works in normal repos and worktrees. On POSIX the state file is created mode `0600`, the directory mode `0700`.
- State is bounded to the 200 most recent events. New intake may evict older metadata. Lock conflicts skip an event instead of blocking an agent. A stale lock after a crash must be cleared manually after inspecting the process; the hook does not override it.
- No network requests, semantic inference, or transcript access. Anyone with local access to the repository's Git administrative data may still access these event records. This is **metadata minimization, not encryption**.
- To delete this optional collection, disable its host hooks first, then explicitly delete the local `project-skill-architect/events.json` file. Never delete the Git directory or existing baseline; do not delete anything automatically. The developer controls local retention and backups.

## Configuration review and install

The canonical skill must already be installed in `.agents/skills/project-skill-architect`. For *new* host configs:

```bash
python .agents/skills/project-skill-architect/scripts/integrate.py --repo . --hosts codex,claude --collect-failures
# Review the generated config in scripts/integrate.py. Only with approval:
python .agents/skills/project-skill-architect/scripts/integrate.py --repo . --hosts codex,claude --collect-failures --apply
```

`--collect-failures` is **absent by default** and changes neither the existing v4 hooks nor GitHub CI. The existing `SessionStart` checkpoint behavior remains. **Already-installed v4 configs are never silently migrated**: the command returns BLOCK and a human must review/merge the additional hook stanza manually. Trust and run the hooks only on trusted project checkouts. The generated commands contain local absolute paths and must be regenerated after moving the checkout. Native hooks must be validated in a real host session before claiming automatic capture is operational.

## Review workflow — avoid false positives

From the repository root, review sanitized event IDs:

```bash
python .agents/skills/project-skill-architect/scripts/agent_events.py inspect --repo .
```

`inspect` is read-only; it shows the number of events and sessions, category totals, and the last 20 redacted records (opaque event/session IDs, host, category and timestamp). It shows **no error descriptions**, so reviewers must independently verify any claim that selected events belong to the *same underlying workflow* using their normal project evidence. The CLI cannot make that classification.

Once two independently reviewed occurrences from **distinct sessions** are selected, label them with a stable workflow topic and run:

```bash
python .agents/skills/project-skill-architect/scripts/agent_events.py evaluate \
  --repo . --topic deployment-workflow --event-ids <event-id-1> <event-id-2>
```

The handoff creates in-memory v5-compatible `agent-failure` observations with unique occurrences. `evolution.assess` can return `review_recommended` for the existing workflow, **not** `create_skill`. Existing manually reviewed decisions can be applied using `--decisions /path/to/decisions.json`. It does not update that file or any baseline.

Review priority: verify incident equality and root cause; inspect existing project instructions and relevant skills; prefer `no change` or an adjustment to an existing skill; only suggest one distinct, recurring, triggerable, verifiable new skill after explicit authorization. Don't treat tool failure counts as competency measurements or automatically blame the agent.

## Source documentation

- Codex hook events and `PostToolUse` input: https://learn.chatgpt.com/docs/hooks
- Claude Code `PostToolUseFailure`: https://code.claude.com/docs/en/hooks
