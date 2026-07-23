from __future__ import annotations

import asyncio
from inspect import Parameter, Signature
import json
from pathlib import Path
import sys
from typing import Any, Optional

from api_surface_sync.sdk import OperationClient, OperationContractError


class _CliInputError(ValueError):
    pass


def _json_group_class(base: type[Any], sensitive_state: dict[str, bool]):
    try:
        from typer._click import ClickException
    except ImportError:
        from click import ClickException
    from typer.core import TyperGroup

    if not issubclass(base, TyperGroup):
        raise TypeError("Typer application group class must inherit TyperGroup")

    class JsonGroup(base):
        def main(self, *args: Any, standalone_mode: bool = True, **kwargs: Any) -> Any:
            parser_exit_code: int | None = None
            try:
                result = super().main(
                    *args,
                    standalone_mode=False,
                    **kwargs,
                )
            except ClickException as exc:
                message = (
                    "invalid command input"
                    if sensitive_state["present"]
                    else str(exc)
                )
                _emit({"success": False, "error": message})
                if standalone_mode:
                    parser_exit_code = exc.exit_code
                    result = None
                else:
                    return exc.exit_code
            if parser_exit_code is not None:
                raise SystemExit(parser_exit_code)
            if standalone_mode and isinstance(result, int) and result:
                raise SystemExit(result)
            return result

    return JsonGroup


def add_commands(app: Any, client: OperationClient) -> None:
    import typer
    from typer.core import TyperGroup

    if hasattr(app, "info"):
        if getattr(app, "registered_callback", None) is None:
            app.callback()(lambda: None)
        state = getattr(app, "_api_surface_sync_sensitive_state", None)
        if not isinstance(state, dict):
            state = {"present": False}
            app._api_surface_sync_sensitive_state = state
            configured = getattr(app.info, "cls", None)
            app._api_surface_sync_base_group = (
                configured if isinstance(configured, type) else TyperGroup
            )
        state["present"] = state["present"] or any(
            bool(item.metadata.get("sensitive"))
            for item in client.snapshot.all()
        )
        app.info.cls = _json_group_class(
            app._api_surface_sync_base_group,
            state,
        )
    for item in client.snapshot.all():
        command_name = item.name.replace("_", "-")

        def command(
            operation_name=item.name,
            operation_metadata=item.metadata,
            **inputs: Any,
        ) -> None:
            try:
                payload = _read_payload(
                    inputs,
                    sensitive=bool(operation_metadata.get("sensitive")),
                )
            except _CliInputError as exc:
                _emit({"success": False, "error": str(exc)})
                raise typer.Exit(2) from exc
            try:
                result = asyncio.run(client.run(operation_name, payload))
            except OperationContractError as exc:
                _emit(
                    {
                        "success": False,
                        "error": _error_message(
                            exc,
                            sensitive=bool(operation_metadata.get("sensitive")),
                            fallback=f"{exc.phase} validation failed",
                        ),
                    }
                )
                raise typer.Exit(3) from exc
            except Exception as exc:
                _emit(
                    {
                        "success": False,
                        "error": _error_message(
                            exc,
                            sensitive=bool(operation_metadata.get("sensitive")),
                            fallback="operation failed",
                        ),
                    }
                )
                raise typer.Exit(4) from exc
            try:
                response = result.model_dump(mode="json", by_alias=True)
            except Exception as exc:
                _emit(
                    {
                        "success": False,
                        "error": _error_message(
                            exc,
                            sensitive=bool(operation_metadata.get("sensitive")),
                            fallback="response serialization failed",
                        ),
                    }
                )
                raise typer.Exit(3) from exc
            _emit({"success": True, "result": response})

        command.__name__ = item.name
        command.__doc__ = item.summary
        command.__signature__ = Signature(  # type: ignore[attr-defined]
            parameters=[
                Parameter(
                        "input_json",
                        Parameter.KEYWORD_ONLY,
                        annotation=Optional[str],
                    default=typer.Option(None, "--input-json"),
                ),
                Parameter(
                        "input_file",
                        Parameter.KEYWORD_ONLY,
                        annotation=Optional[Path],
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
    input_json = inputs["input_json"]
    input_file = inputs["input_file"]
    use_stdin = inputs["stdin"]
    selected = sum(value is not None for value in (input_json, input_file)) + int(
        use_stdin
    )
    if selected != 1:
        raise _CliInputError(
            "choose exactly one of --input-json, --input-file, or --stdin"
        )
    if sensitive and not use_stdin:
        raise _CliInputError("sensitive operations require --stdin")
    if input_json is not None:
        raw = input_json
    elif input_file is not None:
        try:
            raw = input_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise _CliInputError(f"cannot read input file: {exc}") from exc
    else:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _CliInputError("input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise _CliInputError("input JSON must be an object")
    return payload


def _emit(value: dict[str, Any]) -> None:
    import typer

    typer.echo(json.dumps(value, separators=(",", ":")))


def _error_message(
    error: Exception,
    *,
    sensitive: bool,
    fallback: str,
) -> str:
    return fallback if sensitive else str(error)
