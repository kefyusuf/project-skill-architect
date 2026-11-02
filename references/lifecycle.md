# Skill architecture lifecycle: Adopt and Evolve

## Adopt: entering an existing project without damaging it

1. **Read-only inventory**: locate instructions, skills, scripts, repo manifest(s), CI, tests, branch status, relevant commits, and prior architecture decisions. Inspect bounded, pertinent evidence rather than recursively dumping source files.
2. **Reconstruct current contracts**: identify each skill's trigger, non-trigger, outputs, quality checks, permissions, owner/source path, and users/hosts; distinguish confirmed behavior from assumptions.
3. **Compare stated intent with repository reality**: look for outdated commands, unverified test claims, conflicting rules, duplicate skill names, stale stack references, and missing host discovery.
4. **Preserve-before-propose**: report what stays unchanged. Do not replace working skills just because they do not match this template. Avoid adding global policies to a mature project without user approval.
5. **Minimal compatibility plan**: when multiple agents are used, define one canonical source and only the verified adapters needed. Distinguish copied adapters from canonical skill definitions.
6. **Baseline**: if a project decision log exists, read it; otherwise summarize findings in the response. Create a persistent baseline only if the user requests it.

## Evolve: evidence-based change detection

For deterministic **change signals** and manual checkpoint invocation, see [checkpoints.md](checkpoints.md). This is not a skill-generation decision engine; the detector does not modify files.

Evaluate only when *invoked* at a meaningful checkpoint or via an approved external trigger. Potential signals include:

- New repeated development workflow or explicit user requirement.
- Material architectural/stack boundary change that makes an existing skill wrong.
- Same class of agent error observed **at least twice** (guideline, not a mandatory mathematical rule), despite existing instructions.
- Repeated CI failures or review comments attributable to a missing, ambiguous, or obsolete workflow.
- Significant new permission, deployment, data-protection, or review risk.
- Addition/removal of a coding-agent host or changes in its documented skill discovery.
- Skills unused or redundant across meaningful tasks, or materially conflicting with established instructions.

A single isolated mistake is normally insufficient. A specific high-impact risk or an explicit user requirement can justify a proposal immediately. Avoid speculative suggestions based only on file count, number of dependencies, or presence of a framework.

## Decision order

1. **No change** if existing rules and workflows remain adequate.
2. **Repair existing instruction/skill** if ambiguous, stale, or missing an acceptance check.
3. **Merge** overlapping workflows or remove obsolete duplication if safe.
4. **Add** a new skill only if the workflow is distinct, repeatable (or high-risk), actionable, triggerable, and verifiable.
5. **Retire** a skill only with evidence of obsolescence, zero remaining callers, and explicit approval. Prefer deprecate/mark for review when uncertain.
6. **Use tools/hooks/CI** instead when the missing behavior is event detection or enforcement, not task instructions.

Rank candidates by verified user impact, urgency/risk, confidence, implementation effort, and maintenance overhead. At an ordinary checkpoint, present at most one highest-value improvement; the user can ask for a full audit if more changes are desired.

## Proposal card format

```text
Checkpoint: [what triggered this review]
Evidence: [user answer, path, failing check, or observed repeated error]
Current behavior: [what already exists]
Recommendation: [keep | revise | merge | add | retire | no change]
Why now: [impact and cost; explain why existing mechanisms are insufficient]
Proposed location/hosts: [canonical path and required adapters]
Acceptance evidence: [positive trigger, negative trigger, measurable result]
Authorization needed: [files/permissions/external systems]
Deferred alternatives: [briefly state why]
```

## Avoid noisy or circular suggestions

- Do not propose the same declined change again without changed evidence.
- Do not ask for project details already established by repository evidence or earlier user responses.
- Do not manufacture a recurring failure from one anecdote.
- Do not autonomously rewrite skill definitions in the middle of unrelated application changes.
- Do not let a skill optimize itself for more skills; the target is a smaller and more dependable workflow.
- Separate **suggestion capability during an active task** from **actual future monitoring**. To monitor future events, a user-approved platform trigger is required.

## Exit / success conditions

- Every recommended change has traceable evidence and clear non-trigger.
- The project has no unnecessary duplicate definitions across agent hosts.
- Existing instructions are preserved unless explicitly revised.
- The proposed change can be verified in at least one realistic scenario.
- A recommendation does not block the real user's task unless a specific safety/authorization issue requires it.
