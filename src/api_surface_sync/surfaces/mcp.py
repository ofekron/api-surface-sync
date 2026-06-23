from __future__ import annotations

from inspect import Parameter, Signature
from typing import Any

from pydantic_core import PydanticUndefined

from api_surface_sync.registry import OperationRegistry


def add_tools(
    server: Any,
    registry: OperationRegistry,
    *,
    tool_registry: dict[str, Any] | None = None,
) -> None:
    for item in registry.all():

        async def tool(operation=item, **payload: Any) -> Any:
            result = await operation.run(payload)
            return result.value.model_dump(mode="json")

        tool.__name__ = item.name
        tool.__doc__ = item.summary
        tool.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=_parameters_for_model(item.request_model),
            return_annotation=item.response_model,
        )
        if tool_registry is not None:
            tool_registry[item.name] = tool
        server.tool()(tool)


def _parameters_for_model(model: type[Any]) -> list[Parameter]:
    parameters = []
    for name, field in model.model_fields.items():
        default = Parameter.empty
        if not field.is_required():
            if field.default is not PydanticUndefined:
                default = field.default
            elif field.default_factory is not None:
                default = field.default_factory()
        parameters.append(
            Parameter(
                name,
                Parameter.KEYWORD_ONLY,
                annotation=field.annotation,
                default=default,
            )
        )
    return parameters
