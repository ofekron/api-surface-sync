from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any

from api_surface_sync.registry import OperationRegistry


def add_routes(app: Any, registry: OperationRegistry, *, prefix: str = "") -> None:
    for item in registry.all():
        route_path = f"{prefix}/{item.name}".replace("_", "-")

        async def route(payload: Any, operation=item) -> Any:
            result = await operation.run(payload)
            return result.value

        route.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=[
                Parameter(
                    "payload",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=item.request_model,
                )
            ],
            return_annotation=item.response_model,
        )
        app.post(route_path, response_model=item.response_model, summary=item.summary)(route)
