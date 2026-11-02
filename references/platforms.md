# Platform portability and installation

**Checked against public vendor documentation on 2026-11-01.** Platform versions and discovery behavior can change. Verify host support before writing adapters, especially for unlisted runtimes.

| Host | Supported project skill root | Shared `.agents/skills/` | Details |
|---|---|---|---|
| Codex | `.agents/skills/` | Native | Repo-level skills discovered from current directory through repo root |
| Cursor | `.cursor/skills/`, `.agents/skills/` | Native | Also recognizes Claude-compatible locations; avoid ambiguous duplicate names |
| Gemini CLI | `.gemini/skills/`, `.agents/skills/` | Native alias | Skill activation may request explicit user consent |
| OpenCode | `.opencode/skills/`, `.agents/skills/` | Native compatibility | Skills may be disabled by agent-level permissions |
| Claude Code | `.claude/skills/` | **Do not assume** | Install or synchronize a compatibility copy from the canonical definition |
| VS Code Copilot | `.github/skills/` (also other locations per harness) | Supported in some harnesses | Check which configured harness is being used before choosing the path |
| Unknown host | Host-specific verified directory | Unknown | Confirm native skills, activation semantics, permissions, and file layout |

Official docs:

- Standard: https://agentskills.io/specification
- Codex / ChatGPT: https://learn.chatgpt.com/docs/build-skills
- Claude: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Cursor: https://cursor.com/docs/skills
- Gemini CLI: https://geminicli.com/docs/cli/skills/
- OpenCode: https://opencode.ai/docs/skills
- VS Code: https://code.visualstudio.com/docs/agent-customization/agent-skills

## Source-of-truth policy

1. Choose one **authoring source**, usually `.agents/skills/<name>/` for cross-agent projects. If an existing project already uses a different source, do not migrate solely for aesthetics.
2. Never manually maintain independently edited copies. Treat `.claude/skills/<name>/` or `.github/skills/<name>/` copies as **derived** and verify consistency.
3. Do not place same-named independent definitions in multiple roots. Some hosts read multiple roots and may override, duplicate, or select a different version.
4. Where distribution is necessary, prefer a safe, explicitly invoked synchronization. A symlink is an alternative only if the host and operating system support it; Windows symlink permissions and remote agents may differ.
5. Do not auto-create `CLAUDE.md`, `AGENTS.md`, hooks, cron jobs, CI workflows, or MCP configs just to distribute a skill. These are separate choices with different blast radii.
6. Shared files must not assume an unavailable tool name, proprietary CLI instruction, `allowed-tools` feature, context-fork behavior, or host-specific model-invocation metadata. Put optional host-specific variants in adapters only when needed.

## Optional guarded distribution

The included tool is **not a daemon** and does not modify anything unless `--apply` is passed.

```bash
# Preview installing THIS skill for Codex, Cursor, Gemini, and OpenCode:
python scripts/distribute.py --source . --repo /path/to/repo --targets common

# Preview adding a Claude Code compatibility copy:
python scripts/distribute.py --source . --repo /path/to/repo --targets common,claude

# Perform explicit installation after review:
python scripts/distribute.py --source . --repo /path/to/repo --targets common,claude --apply

# To distribute a project skill already authored at .agents/skills/<name>:
python /path/to/project-skill-architect/scripts/distribute.py \
  --source /path/to/repo/.agents/skills/<name> \
  --repo /path/to/repo --targets claude --apply
```

If an installation target is already owned by another tool or modified since the last sync, distribution stops without silently overwriting it. Compatibility copies contain a tool-created ownership manifest. Protect externally edited copies by keeping the canonical source in source control.

## Persistent discovery is separate from scheduling

Project instructions can invite an agent to activate this skill at meaningful checkpoints *in a live session*. A hook, CI job, or explicitly scheduled invocation can enable later/conditional checks if supported and permitted. A Markdown description alone cannot wake an inactive agent, observe uncommitted work, or ensure reliable automatic activation.

For a user-approved optional project instruction, adapt the host instruction file rather than inserting all of SKILL.md:

> At major architecture changes, repeated workflow failures, agent migrations, or PR/release checkpoints, consider invoking `project-skill-architect` for a brief evidence-based skill-architecture review. Recommend at most one useful change; do not edit skill files without authorization or interrupt normal tasks for low-value housekeeping.
