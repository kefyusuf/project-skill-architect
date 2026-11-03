# Skill architecture decision rules

## Assign needs to the right mechanism

| Need | Prefer | Notes |
|---|---|---|
| Persistent project rules applicable to nearly every task | Existing host instructions (`AGENTS.md`, `CLAUDE.md`, etc.) | Respect existing sources of truth; avoid duplicating policies |
| Repeatable multistep task with a clear trigger and verifiable result | `SKILL.md` | On demand, not a background scheduler |
| Task-specific facts, examples, standards, domain notes | Focused `references/*.md` | Load only when needed |
| Stable deterministic checks and transformations | Existing test commands or `scripts/` | Do not invent commands; test scripts |
| Work triggered by commits, changes, schedules, CI, or external events | Host hooks / CI / scheduling | Must be supported, installed and approved; skill text alone does not run |
| External data access or privileged operations | Verified tool/MCP integration | A skill cannot grant permission |
| Context isolation or parallel workers | Host-specific subagent, if supported | Not an interchangeable portable Agent Skill mechanism |
| One-off work, speculative feature, or already-covered rule | No new artifact | Avoid unnecessary maintenance |

Do not create or alter host instruction files, hooks or CI just because the table mentions them.

## Five gates for a new skill

1. **Triggerable**: a realistic user request or task state activates it (and a clear negative case does not).
2. **Repeatable or high-risk**: a stable workflow is expected more than once, or a risky procedure demands a checklist.
3. **Distinct**: an existing skill, instruction, or tool cannot solve it adequately with a smaller revision.
4. **Actionable**: available capabilities and inputs make the steps possible.
5. **Verifiable**: there is observable evidence distinguishing success, failure, and blocked status.

If a gate fails: defer, revise an existing artifact, or recommend no change. Merely introducing a new programming language, framework or folder does not automatically justify new skills.

## Minimize duplication and interference

- Each skill owns one distinguishable workflow and has explicit positive/negative trigger examples.
- Do not require every ordinary coding turn to load an auditing skill.
- Keep SKILL.md concise, with references one level deep; no multi-skill chains requiring hidden activation behavior.
- Do not embed privileged actions or deployment instructions not supported by the actual project.
- Detect duplicate names across `.agents/skills`, `.claude/skills`, `.cursor/skills`, `.gemini/skills`, `.opencode/skills` and `.github/skills`. Different clients may choose differently when multiple identical names exist.
- For generated compatibility copies, distinguish intentional derived mirrors from accidental independent forks; compare content/manifest before overwriting.
- Respect repository-specific branches, CI gates, review policy, documentation language, security and attribution decisions.

## Acceptance criteria examples

**Test-to-review workflow**: triggers only when requested or before a designated handoff; reads actual test commands; emits observed pass/fail evidence; never treats missing commands as passed; does not trigger for a product brainstorming discussion.

**Database migration review**: triggers on an actual schema migration; assesses impact and reversibility using repository patterns; never executes production mutations without approval; does not trigger for a README edit.

**Skill evolution**: triggers at a meaningful checkpoint or explicit request; compares existing mechanisms to new evidence; recommends at most one change in a routine task; does not manufacture skills based on one isolated failure; does not promise unattended monitoring.
