# AGENTS.md

## Core Rule

This repo is generic tooling. Keep TestApe as a consumer, not a dependency.

## Development Rules

- Preserve one source of truth: operation contracts live in the registry, surfaces bind to it.
- Keep surface adapters thin. Business logic belongs in consuming projects.
- Do not add TestApe-specific names, flows, adapters, FS-DB concepts, or expert-agent assumptions here.
- Use Pydantic models for request and response contracts.
- Prefer small modules with clear boundaries.
- Add tests for every behavior change.
- Delete dead code when a change makes it unused.
- Keep README and `.agents/skills/project-structure/SKILL.md` current when material project facts change.

## Git Rules

- Stage only files changed for the current task.
- Do not use `git add -A` or `git add .`.
- Do not rewrite unrelated work.

