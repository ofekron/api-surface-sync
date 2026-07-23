---
name: project-structure
description: Fast project map for API Surface Sync, a Python library that maps typed operation registries to SDK, CLI, REST, and MCP surfaces. Use before locating core registry code, surface adapters, tests, packaging, or project conventions.
---

# API Surface Sync Project Structure

API Surface Sync is a generic Python library for defining typed operations once and exposing them through multiple API surfaces. A sealed registry snapshot owns the contracts, one validating client delegates to an injected executor, and SDK, structured CLI, REST, and MCP adapters bind to that client without owning business logic.

## Routing

| Need | Read |
|---|---|
| Directory layout and ownership | `sections/directory-map.md` |
| Architecture and invariants | `sections/architecture.md` |
| Run and test commands | `sections/running.md` |
| Project conventions | `sections/conventions.md` |

## Keeping This Skill Current

Agents must update this skill when material project facts change: public surfaces, package layout, operation contract rules, test strategy, release workflow, or architecture invariants.
