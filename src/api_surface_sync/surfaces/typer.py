from __future__ import annotations

import asyncio
from inspect import Parameter, Signature
import json
from pathlib import Path
import sys
from typing import Any

from api_surface_sync.sdk import OperationClient


def add_commands(app: Any, client: OperationClient) -> None:
    import typer

    for item in client.snapshot.all():
        command_name = item.name.replace("_", "-")

        def command(
            operation_name=item.name,
            operation_metadata=item.metadata,
            **inputs: Any,
        ) -> None:
            payload = _read_payload(inputs, sensitive=bool(operation_metadata.get("sensitive")))
            result = asyncio.run(client.run(operation_name, payload))
            typer.echo(result.model_dump_json(by_alias=True))

        command.__name__ = item.name
        command.__doc__ = item.summary
        command.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=[
                Parameter(
                    "input_json",
                    Parameter.KEYWORD_ONLY,
                    annotation=str | None,
                    default=typer.Option(None, "--input-json"),
                ),
                Parameter(
                    "input_file",
                    Parameter.KEYWORD_ONLY,
                    annotation=Path | None,
                    default=typer.Option(None, "--input-file"),
                ),
                Parameter(
                    "stdin",
                    Parameter.KEYWORD_ONLY,
                    annotation=bool,
                    default=typer.Option(False, "--stdin"),
                ),
            ],
            return_annotation=None,
        )
        app.command(name=command_name)(command)


def _read_payload(inputs: dict[str, Any], *, sensitive: bool) -> dict[str, Any]:
    import typer

    input_json = inputs["input_json"]
    input_file = inputs["input_file"]
    use_stdin = inputs["stdin"]
    selected = sum(value is not None for value in (input_json, input_file)) + int(
        use_stdin
    )
    if selected != 1:
        raise typer.BadParameter(
            "choose exactly one of --input-json, --input-file, or --stdin"
        )
    if sensitive and not use_stdin:
        raise typer.BadParameter("sensitive operations require --stdin")
    if input_json is not None:
        raw = input_json
    elif input_file is not None:
        raw = input_file.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("input JSON must be an object")
    return payload
