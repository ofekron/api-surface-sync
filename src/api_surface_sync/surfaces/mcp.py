from __future__ import annotations

from typing import Any

from api_surface_sync.registry import OperationRegistry


def add_tools(server: Any, registry: OperationRegistry) -> None:
    for item in registry.all():

        async def tool(payload: dict[str, Any], operation=item) -> dict[str, Any]:
            result = await operation.run(payload)
            return result.value.model_dump(mode="json")

        tool.__name__ = item.name
        tool.__doc__ = item.summary
        server.tool()(tool)

