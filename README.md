# API Surface Sync

Define typed Python operations once and expose them as SDK, CLI, REST, and MCP surfaces.

The core idea is simple: keep behavior in one canonical operation registry, then let every public surface bind to that registry instead of hand-maintaining parallel implementations.

```python
from pydantic import BaseModel
from api_surface_sync import OperationRegistry

registry = OperationRegistry()

class EchoRequest(BaseModel):
    text: str

class EchoResponse(BaseModel):
    text: str

@registry.operation("echo", request_model=EchoRequest, response_model=EchoResponse)
def echo(request: EchoRequest) -> EchoResponse:
    return EchoResponse(text=request.text)
```

From the same registry:

```python
from api_surface_sync import OperationClient
from api_surface_sync import export_openapi
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools
from api_surface_sync.surfaces.typer import add_commands
```

## What This Is For

- Python projects with a real internal API that must appear as multiple surfaces.
- Tools that need SDK, CLI, REST, and MCP parity.
- Projects where OpenAPI is useful, but not the natural source of truth.

## What Stays Generic

- Operation registration
- Pydantic request and response contracts
- Surface adapters
- Schema export
- Context/auth hooks as the project evolves

Project-specific concepts belong in the consuming project, not in this library.

## Install

```bash
pip install "api-surface-sync @ git+https://github.com/ofekron/api-surface-sync.git"
```

After a PyPI release:

```bash
pip install api-surface-sync
```

For local development:

```bash
pip install -e ".[dev]"
pytest
```

## SDK Languages

`export_openapi(registry, title="My API")` emits an OpenAPI 3.1 contract. Use that contract with OpenAPI Generator, Speakeasy, Stainless, Fern, or custom templates to generate TypeScript, Go, Rust, Java, Swift, or other SDKs from the same operation source.

## Status

Early extraction-stage project. The first target consumer is TestApe, but the public contract must remain useful for the common case: one typed Python operation model exposed through several standard API surfaces.
