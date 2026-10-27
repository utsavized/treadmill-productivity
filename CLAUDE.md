# How we work in this repo

This repo is built with **spec-driven development**. We figure out what to build in text, where changing your mind is cheap, and only then write code.

**Idea → FRD → Building blocks → Spec → Inspect and adapt → Implement**

## Roles

Each role is a subagent in `.claude/agents/`. Use the one that matches the phase.

| Phase | Role | Owns |
|---|---|---|
| Idea → FRD | `product-manager` | `docs/frd.md`: what we're building and why |
| FRD → building blocks | `solutions-architect` | `docs/architecture.md`: data sources, technology, tradeoffs |
| Spec → implementation | `principal-engineer` | `docs/spec.md` and the code |

Utsav makes every final call. Agents propose, question and push back. They don't decide.

## Ground rules for every agent

1. **No code before the spec is approved.** Until Utsav says the spec is approved, the only files that change are in `docs/`. A small throwaway spike to answer a research question is fine if it lives in `spikes/` and is deleted or clearly marked.
2. **Ask before you assume.** If something is ambiguous, ask. Don't fill the gap silently. Ask a few sharp questions at a time, not a wall of them.
3. **Push back.** If a requirement is vague, contradictory or unmeasurable, say so and propose an alternative. A good question is worth more than a fast answer.
4. **Input is often dictated.** Utsav talks to you by voice, so expect transcription slips. If a word looks wrong, confirm it rather than guessing.
5. **Scale the docs to the work.** Keep every doc as short as it can be while still being unambiguous. No filler, no boilerplate sections that say nothing.
6. **Personal data stays local.** Never commit exported health data, activity logs or tokens. Real data goes in `data/`, which is ignored by git. Test data is built inside the tests; the repository ships no data files.

## Decision log

Every doc in `docs/` ends with a `## Decisions` section. Whenever something gets decided, add a row:

| # | Decision | Rejected alternatives | Why | Raised by |
|---|---|---|---|---|
| D1 | Short statement of what we chose | What else was on the table | The reason, in one or two lines | Utsav, or the agent's role |

- Number decisions across the whole project (D1, D2, ...), not per doc, so they can be referenced anywhere.
- Never delete a decision. If one is reversed, add a new row that says "Reverses D4" and why.
- Unresolved questions go in a `## Open questions` section above the decision log. When one is answered, move it into a decision.

## Versions and commits

The history of the docs is part of the story, so every revision is its own commit.

- Each doc has a version line at the top: `Version: v3 · <one-line summary of the latest change>`.
- After each meaningful revision (a requirement added, cut or changed, a gap closed, a decision made), bump the version and commit **only that doc**, with this message format:

  `<doc> v<N>: <what changed>, <why>`

  For example: `spec v3: exclude idle time, VS Code open while I'm away shouldn't count`.
- Don't batch several revisions into one commit, and don't mix doc changes with code changes.
- During implementation, commit code in small steps that reference the spec section they implement, for example `implement §4.2 effort score`.

## If implementation finds a gap in the spec

Stop. Don't improvise in code. Describe the gap, propose a spec change, wait for Utsav's call, update `docs/spec.md` (new version, new decision row), commit the spec, then continue implementing.
