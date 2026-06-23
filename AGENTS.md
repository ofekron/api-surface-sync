# AGENTS.md

Full working rules live in [`CLAUDE.md`](CLAUDE.md). Read it first — it is the single source for how to work in this repo. This file is a short pointer for tooling that looks for `AGENTS.md`.

## Core Rule

This repo is generic tooling. Keep consumers (e.g. TestApe) as users of the library, not concepts baked into it.

## Quick reference

- One source of truth: operation contracts live in the registry; surfaces bind to it.
- Surface adapters stay thin. Business logic belongs in consuming projects.
- No consumer-specific names, flows, adapters, storage, or agent assumptions here.
- Pydantic models for request/response contracts.
- Every behavior change ships with tests; bug fixes ship with a fail-before/pass-after test.
- Stage only files you changed. Never `git add -A` / `git add .`. Never rewrite unrelated work.
