from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any

from api_surface_sync.sdk import OperationClient


def add_routes(app: Any, client: OperationClient, *, prefix: str = "") -> None:
    normalized_prefix = prefix.rstrip("/")
    for item in client.snapshot.all():
        route_path = f"{normalized_prefix}/{item.name.replace('_', '-')}"

        async def route(payload: Any, operation_name=item.name) -> Any:
            return await client.run(operation_name, payload)

        route.__name__ = item.operation_id.replace(".", "_").replace("-", "_")
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
        app.post(
            route_path,
            response_model=item.response_model,
            summary=item.summary,
            operation_id=item.operation_id,
        )(route)
