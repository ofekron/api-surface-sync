# API Surface Sync — working rules

> Generic tooling repo. One canonical operation registry → SDK + CLI + REST + MCP surfaces.
> Keep it generic and reusable; consumers (e.g. TestApe) bring their own domain concepts.

## Scope discipline (the one rule that defines this repo)

- This library solves exactly one thing: **a typed Python operation, defined once, exposed through standard API surfaces.**
- No consumer-specific names, flows, adapters, storage, or agent assumptions ever land here. If a concept only makes sense in one downstream project, it belongs in that project.
- Surface adapters stay thin. Business logic lives in the consumer's handlers, never in an adapter.
- Differences between callers are expressed as parameters, never as a copied-and-tweaked second code path.

## Single source of truth

- Operation contracts (Pydantic request/response models) live once, in the registry. Every surface binds to it; none reimplements it.
- One implementation per behavior. When a new case looks similar, extend the single path (parameter, subclass, strategy) — do not fork a parallel one.
- If you find a duplicate, consolidate to one owner and delete the rest.
- Caching/projection is allowed for performance, but the registry is always the source; on conflict the source wins.

## Coding rules

- Work top-down: write the usage as if the function exists, then implement it.
- Prefer early returns; keep nesting shallow.
- Import from the project root, not deep relative paths.
- Keep files short; split long files logically.
- No hacks without explicit approval. No hard-coded placeholder values shown when no real value exists.
- No backward-compat shims unless explicitly asked.
- No fallback-on-error unless explicitly asked.
- **No tech debt:** when a change makes code, imports, types, or files unused — delete them.
- Abstraction + DRY, but simplicity and readability win.

## Tests are the proof

- Every behavior change ships with tests.
- Every bug fix ships with a test that **fails before the fix and passes after**.
- `pytest` must be green before commit.
- A core invariant test must assert every registered operation appears on every surface (SDK, CLI, REST, MCP) — parity is mechanical, not manual.

## Comments & docs

- No README/docs/comments unless they describe current state and add real value. Never reference what code "used to" do.
- Comments are untrusted hints; the code is authoritative.
- Don't create markdown/summary files unless asked.

## Git

- Stage ONLY the files you changed. Never `git add -A` / `git add .` / `git stash`.
- Leave unrelated changes alone.
- Never create a branch unless explicitly told to.
- Commit + push after a turn that wrote files.

## Multi-writer hygiene

- Other agents may edit concurrently. Read a file before editing it; never write from a stale snapshot.
- Prefer targeted edits over full-file overwrites.

## Keep the map current

- Update `README.md` and `.agents/skills/project-structure/SKILL.md` when material facts change: public surfaces, package layout, contract rules, test strategy, release workflow, or architecture invariants.
