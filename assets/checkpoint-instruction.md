# Optional agent instruction snippet

Place a concise version **only with user approval** in an existing project instruction file (e.g. `AGENTS.md` for Codex, `CLAUDE.md` for Claude Code). Do not replace established rules or install a hook implicitly.

> At meaningful checkpoints—new architecture boundaries, recurring workflow failures, changed project policies, agent integrations, and PR/release review—evaluate whether existing skills still fit. When evidence is available, run `project-skill-architect`'s read-only `scripts/checkpoint.py` using a reviewed baseline or explicit Git base revision. Interpret resulting signals against approved project instructions, existing skill contracts, and actual task outcomes; a changed file does not itself justify a new skill. Prefer no change or a small revision; suggest at most one improvement during ordinary development. Do not modify instructions, skills, CI, or hooks without authorization. Do not repeatedly resurface declined suggestions without new evidence.

This advisory text works only when an agent actually reads and follows the project instructions. It does not guarantee activation, start background monitoring, or enable unsupervised project changes. Use [references/checkpoints.md](../references/checkpoints.md) for the precise review and baseline-acknowledgment protocol.
