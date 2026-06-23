from __future__ import annotations

import asyncio
from inspect import Parameter, Signature
from typing import Any

from pydantic_core import PydanticUndefined

from api_surface_sync.registry import OperationRegistry


def add_commands(app: Any, registry: OperationRegistry) -> None:
    for item in registry.all():
        command_name = item.name.replace("_", "-")

        def command(operation=item, **payload: Any) -> None:
            result = asyncio.run(operation.run(payload))
            print(result.value.model_dump_json())

        command.__name__ = item.name
        command.__doc__ = item.summary
        command.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=_parameters_for_model(item.request_model),
            return_annotation=None,
        )
        app.command(name=command_name)(command)


def _parameters_for_model(model: type[Any]) -> list[Parameter]:
    import typer

    parameters = []
    for name, field in model.model_fields.items():
        description = field.description or None
        if field.is_required():
            default = typer.Argument(..., help=description)
            kind = Parameter.POSITIONAL_OR_KEYWORD
        else:
            default_value = None
            if field.default is not PydanticUndefined:
                default_value = field.default
            elif field.default_factory is not None:
                default_value = field.default_factory()
            default = typer.Option(default_value, help=description)
            kind = Parameter.KEYWORD_ONLY
        parameters.append(
            Parameter(
                name,
                kind,
                annotation=field.annotation,
                default=default,
            )
        )
    return parameters
