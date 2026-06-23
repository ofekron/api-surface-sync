from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any

from api_surface_sync.registry import OperationRegistry


def add_tools(server: Any, registry: OperationRegistry) -> None:
    for item in registry.all():

        async def tool(payload: dict[str, Any], operation=item) -> dict[str, Any]:
            result = await operation.run(payload)
            return result.value.model_dump(mode="json")

        tool.__name__ = item.name
        tool.__doc__ = item.summary
        tool.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=[
                Parameter(
                    "payload",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=item.request_model,
                )
            ],
            return_annotation=item.response_model,
        )
        server.tool()(tool)
