from __future__ import annotations

import warnings
from inspect import Parameter, Signature
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import PydanticJsonSchemaWarning
from pydantic_core import PydanticUndefined

from api_surface_sync.sdk import OperationClient


class _Omitted:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<api-surface-sync omitted>"


_OMITTED = _Omitted()


def add_tools(
    server: Any,
    client: OperationClient,
    *,
    tool_registry: dict[str, Any] | None = None,
) -> None:
    for item in client.snapshot.all():

        async def tool(operation_name=item.name, **payload: Any) -> Any:
            payload = {
                name: value for name, value in payload.items() if value is not _OMITTED
            }
            result = await client.run(operation_name, payload)
            return result.model_dump(mode="json", by_alias=True)

        tool.__name__ = item.name
        tool.__doc__ = item.summary
        tool.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=_parameters_for_model(item.request_model),
            return_annotation=item.response_model,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Default value <api-surface-sync omitted> is not JSON serializable",
                category=PydanticJsonSchemaWarning,
            )
            registered_tool = server.tool()(tool)
        if tool_registry is not None:
            tool_registry[item.name] = registered_tool


def _parameters_for_model(model: type[Any]) -> list[Parameter]:
    parameters = []
    for field_name, field in model.model_fields.items():
        name = field.alias or field_name
        annotation = field.rebuild_annotation()
        if field.description:
            annotation = Annotated[annotation, Field(description=field.description)]
        default = Parameter.empty
        if not field.is_required():
            default = field.default if field.default is not PydanticUndefined else _OMITTED
        parameters.append(
            Parameter(
                name,
                Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=default,
            )
        )
    return parameters
