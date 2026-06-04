# Meta-Agentics Transcript Summary — Core Concepts + How-Tos

## Core concepts
- **Main failure mode**: agents “execute and forget” → no learning loop; humans manually maintain memory/prompts/skills.
- **Agent expert**: executes and learns by updating an evolving **mental model** (a data structure).
- **Meta-agentics**: “system that builds the system” — prompts build prompts, agents build agents, skills build skills.
- **3-step expert workflow**: **Plan → Build → Self-improve**.
- **Context delegation**: protect the top-level orchestrator’s context by delegating heavy work to subagents and composing results.
- **Scale compute**: run multiple agents; some fail, some succeed; synthesize for better outcomes.
- **Foundational units**: context, model, prompt, tools (everything else is packaging).

## How-tos (applied to the TD builder project)
- Implement an **expert loop** per domain (retrieval, workflow recipes, builder, validation, deployment):
  - Plan step produces a structured plan + hypotheses.
  - Build step executes, produces diffs/artifacts.
  - Self-improve step turns outcomes into **expertise updates** (rules, recipes, heuristics, counterexamples).
- Store expertise as **structured files** (not prose) with:
  - claims + evidence links (source-of-truth pointers)
  - confidence + last-validated timestamp
  - failure cases + fixes
- Add **meta prompts/agents** that can:
  - generate new expert templates
  - generate eval tasks
  - generate new skills/tools wrappers
- Add **orchestration rules**:
  - small, protected orchestrator prompt
  - subagents limited to one domain each
  - compose outputs into a single validated deliverable
- Add **guardrails**:
  - “code is source of truth” validation
  - tests + canary eval before adopting new expertise or changing code
  - rollback for corrupted expertise
