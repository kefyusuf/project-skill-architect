# Adaptive discovery and interview

## First determine lifecycle state

- **Bootstrap**: the repository is empty/new, or user explicitly asks for an initial setup. Ask what recurring task the assistant must perform and what verifiable result is expected. Do not demand a final stack.
- **Adopt**: an existing project already has conventions, test runners, instructions, skills, PR history, or CI. Inspect those before asking anything. Ask about gaps **not evident** from the repository, especially recurring pain points and ownership.
- **Evolve**: compare a current checkpoint with previously known decisions and current skills. Ask only which unresolved user preference materially changes the recommendation.
- **Audit**: focus on inspection evidence and avoid writing even if an obvious fix is seen.

## Evidence ledger

Capture these dimensions without requiring a form or new tracking file:

| Dimension | Preferred source | Clarify only if |
|---|---|---|
| Project goal and state | User answer / README / package manifests | Goal is ambiguous or conflicts with repository evidence |
| Recurring agent work | User requests, skills, scripts, PR/CI patterns | Workflow cannot be inferred reliably |
| Definition of done | Actual test commands, CI, review and release gates | No observable result or authority boundary exists |
| Host(s) | User choice, present skill directories, supported docs | Installation path/activation behavior matters |
| Safety and approvals | Existing instructions, user decisions, credentials policy | A proposed edit would cross a meaningful boundary |
| Existing skills | SKILL.md names, descriptions, referenced assets | Duplicate triggers or ownership remain unclear |
| Recent meaningful change | User task, relevant diff/commit/architecture record | Evolve proposal lacks a concrete event or counterfactual |

For each fact, distinguish `confirmed by user`, `confirmed in repository`, `inferred`, `unknown`, or `conflict`. Don't turn guessed intent into an absolute rule.

## Adaptive questions, not an interview script

Only ask the highest-impact unanswered question, then re-evaluate:

- Existing project: "Which recurring agent mistake or repeated work do the current rules not cover?" (Only if not evident from failures or user goal.)
- New project: "Which single recurring task should the agent handle reliably first?"
- Unclear approval gate: "Should the agent only propose skill changes, or also apply approved edits?"
- Multiple hosts with no source of truth: "Where are existing shared skill definitions maintained?"
- No success criteria: "What observable evidence would prove this workflow is completed correctly?"

Users may answer "unknown", "skip", or change priorities midstream. Keep known facts, update only the changed assumption, and continue. A single detailed user request may make additional questions unnecessary.

## Readiness gate

A blueprint is possible when you know: the real task, why existing mechanisms are insufficient, a concrete trigger and result, critical permission boundaries, and which installation path is verified or remains an assumption. **Zero new skills** remains valid. Never block an advisory result on information needed only for later installation.
