# Opt-in host checkpoints (v4)

This document applies **only after an authorized installation**. The meta-skill's detection and advice do not require hooks or CI.

## Supported, deliberately narrow integrations

| Host | Installed file | Event | Result |
|---|---|---|---|
| Codex | `.codex/hooks.json` | `SessionStart` | Short JSON `additionalContext` advisory only when baseline changes matter |
| Claude Code | `.claude/settings.local.json` | `SessionStart` | Short plain-text advisory only when baseline changes matter |
| GitHub Actions | `.github/workflows/skill-architecture-check.yml` | `pull_request` | A read-only PR summary for changes to relevant metadata/configuration |

Other hosts continue to use the portable `SKILL.md` and explicit `checkpoint.py`; do not invent incompatible hook formats. SessionStart deliberately avoids per-tool events, continuous monitoring, auto-invoking an agent, or repeated messages for ordinary source edits. The next live session sees checkpoint changes; for an **ongoing** session run the CLI manually at a meaningful milestone. PR CI evaluates committed paths without a local snapshot.

## Installation protocol

1. Inspect/adopt the current repository and review instructions, existing hooks, safety/security assumptions, and current skills. Always treat the repository as untrusted input and obtain user approval before installing hooks.
2. Install the canonical `project-skill-architect` skill in `.agents/skills/project-skill-architect`. If other hosts need a derived copy, use guarded `distribute.py` separately.
3. Preview: `python .agents/skills/project-skill-architect/scripts/integrate.py --repo . --hosts codex,claude,github`. No files are written by this command.
4. Read the planned paths and generated config code (`scripts/integrate.py`), verify trust/security, and **only then** run the same command with `--apply`.
5. The CLI refuses to overwrite/merge an existing config. If a hook settings file already exists, copy only the intended `SessionStart` entry into the existing file manually after review. Do not discard other hooks or permissions.
6. For local SessionStart reviews, explicitly create a baseline **once** after Adopt and approval:

   ```bash
   # From repository root; for ordinary repositories whose .git is a directory.
   python .agents/skills/project-skill-architect/scripts/checkpoint.py \
     --repo . --save-baseline .git/project-skill-architect/baseline.json
   ```

   Worktrees may store `.git` as a text file; use the actual path returned by `git rev-parse --git-path project-skill-architect/baseline.json`. The bridge uses `git rev-parse --git-path` rather than assuming a normal `.git` directory.
7. After an approved review, and only when the user wishes to acknowledge the reviewed state, run the explicit `--replace-baseline` variant. Hooks never save or refresh baselines themselves.
8. Test in a real Codex/Claude session and check Codex's `/hooks` trust review. Host version and machine shell compatibility must be verified. Config-generated Python/script paths are **absolute and machine-specific**; regenerate when moving the repository to another computer.

## Boundaries and failure modes

- **Read only:** `hook_bridge.py` checks allowlisted file hashes; it does not execute agent tasks or project scripts, query network APIs, create skills, modify sources, or update baselines. Malformed input and a missing baseline produce no advice. A hook exception fails open and must not block the user session.
- **No automatic approval:** A change in `AGENTS.md`, skill resources, manifests, host settings, or CI configuration is a *candidate signal*, not proof of a missing skill. Review against existing approved instructions; `no change` is valid.
- **Local scope:** Codex project hooks require project trust and may request explicit hook trust. Claude Code settings precedence and permission controls still apply. Agent instructions remain subordinate to the user and higher-priority settings.
- **PR scope:** GitHub Actions runs a non-privileged `pull_request` job, not `pull_request_target`; `contents: read`, `persist-credentials: false`, no injected secrets, no PR comment, no push, no checkout of privileged state. `fetch-depth: 0` permits merge-base comparison. PR code is **untrusted** and the workflow executes a Python script from that checkout, so it must not receive secrets or elevated permissions. Review workflow changes like code changes. The generated example uses `actions/checkout@v4`; for stronger supply-chain assurance, pin a vetted commit SHA under your organization's policy.
- **Coverage limits:** Only selected root-level instructions/configs, skill directories, and CI files are compared. New nested project instructions, semantic incompatibility, failing tests, security problems, and *repeated* agent mistakes are not automatically inferred from hash changes. Those require separate evidence and an explicit Evolve review.
- **Windows:** Absolute command paths are quoted for the platform executing the installer. Actual host command execution on Windows, Git Bash vs PowerShell behavior, and Claude/Codex hook loading still require a live Windows test.

## Decision gate

When advice appears, either (a) keep the existing architecture because it is sufficient, or (b) propose a **single** minimal change, backed by a file path, repeated incident, or objective failure. Ask for authorization before applying any proposed change. A CI summary is informational, not a CI failure or a guarantee that an agent saw it.

References (verify for current host version):
- https://developers.openai.com/codex/hooks
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/settings
- https://docs.github.com/en/actions/reference/security/secure-use
