# Directory Map

| Path | Purpose |
|---|---|
| `src/api_surface_sync/registry.py` | Canonical operation definitions, validation, and immutable snapshots. |
| `src/api_surface_sync/sdk.py` | Validating client plus local and HTTP executor strategies. |
| `src/api_surface_sync/openapi.py` | OpenAPI export and component/reference validation. |
| `src/api_surface_sync/surfaces/` | Thin adapters for external surfaces. |
| `tests/` | Behavior tests for registry and adapters. |
| `pyproject.toml` | Packaging, dependencies, and pytest configuration. |
| `AGENTS.md` | Contributor and agent rules for this repo. |
