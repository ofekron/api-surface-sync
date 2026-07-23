import asyncio
import json
from pathlib import Path

from pydantic import BaseModel, Field

from api_surface_sync import OperationClient, OperationRegistry
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools
from api_surface_sync.surfaces.typer import add_commands


class EchoRequest(BaseModel):
    text: str
    suffix: str = Field(default_factory=lambda: "!")


class EchoResponse(BaseModel):
    value: str


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, name: str, request: BaseModel):
        self.calls.append((name, request.model_dump(exclude_unset=True)))
        return {"value": f"{request.text}{request.suffix}"}


def build_client() -> tuple[OperationClient, RecordingExecutor]:
    registry = OperationRegistry()

    @registry.operation(
        "echo_now",
        operation_id="echo.run",
        request_model=EchoRequest,
        response_model=EchoResponse,
    )
    def poison_handler(request: EchoRequest) -> EchoResponse:
        raise AssertionError("surface bypassed the injected executor")

    executor = RecordingExecutor()
    return OperationClient(registry, executor), executor


def test_fastapi_route_uses_client_and_shared_operation_id() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    client, executor = build_client()
    app = FastAPI()
    add_routes(app, client, prefix="/api")
    response = TestClient(app).post("/api/echo-now", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json() == {"value": "hello!"}
    route = next(route for route in app.routes if route.path == "/api/echo-now")
    assert route.operation_id == "echo.run"
    assert executor.calls == [("echo_now", {"text": "hello"})]


def test_real_fastmcp_tool_preserves_field_schema_and_uses_client() -> None:
    from mcp.server.fastmcp import FastMCP

    client, executor = build_client()
    server = FastMCP("test")
    add_tools(server, client)

    async def scenario():
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == ["echo_now"]
        assert set(tools[0].inputSchema["properties"]) == {"text", "suffix"}
        assert tools[0].inputSchema["required"] == ["text"]
        assert "payload" not in tools[0].inputSchema["properties"]
        result = await server._tool_manager.call_tool(
            "echo_now",
            {"text": "hello"},
            convert_result=False,
        )
        assert result == {"value": "hello!"}

    asyncio.run(scenario())
    assert executor.calls == [("echo_now", {"text": "hello"})]


def test_real_fastmcp_tool_preserves_alias_constraints_and_factory_semantics() -> None:
    from mcp.server.fastmcp import FastMCP

    factory_calls = 0

    def default_value() -> str:
        nonlocal factory_calls
        factory_calls += 1
        return f"default-{factory_calls}"

    class Request(BaseModel):
        value: str | None = Field(
            default_factory=default_value,
            alias="wire_value",
            description="Optional wire value.",
        )
        label: str = Field(min_length=2)

    class Response(BaseModel):
        value: str | None

    class Executor:
        async def run(self, name: str, request: BaseModel):
            return {"value": request.value}

    registry = OperationRegistry()

    @registry.operation("factory", request_model=Request, response_model=Response)
    def poison_handler(request: Request) -> Response:
        raise AssertionError("surface bypassed the injected executor")

    server = FastMCP("test")
    add_tools(server, OperationClient(registry, Executor()))

    async def scenario():
        tool = (await server.list_tools())[0]
        assert tool.inputSchema["properties"]["wire_value"]["description"] == (
            "Optional wire value."
        )
        assert tool.inputSchema["properties"]["label"]["minLength"] == 2
        assert await server._tool_manager.call_tool(
            "factory", {"label": "ok"}, convert_result=False
        ) == {"value": "default-1"}
        assert await server._tool_manager.call_tool(
            "factory",
            {"wire_value": None, "label": "ok"},
            convert_result=False,
        ) == {"value": None}
        assert await server._tool_manager.call_tool(
            "factory", {"label": "ok"}, convert_result=False
        ) == {"value": "default-2"}

    asyncio.run(scenario())


def test_typer_command_accepts_exactly_one_structured_input(tmp_path: Path) -> None:
    import typer
    from typer.testing import CliRunner

    client, executor = build_client()
    app = typer.Typer()
    app.callback()(lambda: None)
    add_commands(app, client)
    runner = CliRunner()
    json_result = runner.invoke(
        app,
        ["echo-now", "--input-json", '{"text":"json"}'],
    )
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout) == {
        "success": True,
        "result": {"value": "json!"},
    }
    input_path = tmp_path / "request.json"
    input_path.write_text('{"text":"file","suffix":"?"}', encoding="utf-8")
    file_result = runner.invoke(
        app,
        ["echo-now", "--input-file", str(input_path)],
    )
    assert file_result.exit_code == 0
    assert json.loads(file_result.stdout) == {
        "success": True,
        "result": {"value": "file?"},
    }
    stdin_result = runner.invoke(
        app,
        ["echo-now", "--stdin"],
        input='{"text":"stdin","suffix":null}',
    )
    assert stdin_result.exit_code == 3
    assert json.loads(stdin_result.stdout)["success"] is False
    missing_result = runner.invoke(app, ["echo-now"])
    assert missing_result.exit_code == 2
    assert json.loads(missing_result.stdout) == {
        "success": False,
        "error": "choose exactly one of --input-json, --input-file, or --stdin",
    }
    assert executor.calls == [
        ("echo_now", {"text": "json"}),
        ("echo_now", {"text": "file", "suffix": "?"}),
    ]


def test_typer_command_enforces_sensitive_stdin_and_stable_failure_codes() -> None:
    import typer
    from typer.testing import CliRunner

    registry = OperationRegistry()

    @registry.operation(
        "secret",
        request_model=EchoRequest,
        response_model=EchoResponse,
        metadata={"sensitive": True},
    )
    def poison_handler(request: EchoRequest) -> EchoResponse:
        raise AssertionError("surface bypassed the injected executor")

    class FailingExecutor:
        async def run(self, name: str, request: BaseModel):
            raise RuntimeError("handler failed")

    app = typer.Typer()
    app.callback()(lambda: None)
    add_commands(app, OperationClient(registry, FailingExecutor()))
    runner = CliRunner()

    rejected = runner.invoke(
        app,
        ["secret", "--input-json", '{"text":"visible"}'],
    )
    assert rejected.exit_code == 2
    assert json.loads(rejected.stdout) == {
        "success": False,
        "error": "sensitive operations require --stdin",
    }

    failed = runner.invoke(
        app,
        ["secret", "--stdin"],
        input='{"text":"hidden"}',
    )
    assert failed.exit_code == 4
    assert json.loads(failed.stdout) == {
        "success": False,
        "error": "operation failed",
    }


def test_typer_command_redacts_sensitive_validation_and_executor_errors() -> None:
    import typer
    from typer.testing import CliRunner

    secret = "SUPERSECRET"
    registry = OperationRegistry()

    @registry.operation(
        "secret",
        request_model=EchoRequest,
        response_model=EchoResponse,
        metadata={"sensitive": True},
    )
    def poison_handler(request: EchoRequest) -> EchoResponse:
        raise AssertionError("surface bypassed the injected executor")

    class SecretExecutor:
        async def run(self, name: str, request: BaseModel):
            if request.text == "executor":
                raise RuntimeError(secret)
            return {"value": [secret]}

    app = typer.Typer()
    app.callback()(lambda: None)
    add_commands(app, OperationClient(registry, SecretExecutor()))
    runner = CliRunner()

    invalid_request = runner.invoke(
        app,
        ["secret", "--stdin"],
        input=json.dumps({"text": [secret]}),
    )
    assert invalid_request.exit_code == 3
    assert json.loads(invalid_request.stdout)["error"] == "request validation failed"

    invalid_response = runner.invoke(
        app,
        ["secret", "--stdin"],
        input='{"text":"response"}',
    )
    assert invalid_response.exit_code == 3
    assert json.loads(invalid_response.stdout)["error"] == "response validation failed"

    executor_failure = runner.invoke(
        app,
        ["secret", "--stdin"],
        input='{"text":"executor"}',
    )
    assert executor_failure.exit_code == 4
    assert json.loads(executor_failure.stdout)["error"] == "operation failed"
    assert secret not in (
        invalid_request.stdout + invalid_response.stdout + executor_failure.stdout
    )


def test_typer_command_wraps_parser_and_handler_validation_errors() -> None:
    import typer
    from pydantic import ValidationError
    from typer.testing import CliRunner

    registry = OperationRegistry()

    @registry.operation(
        "validate",
        request_model=EchoRequest,
        response_model=EchoResponse,
    )
    def poison_handler(request: EchoRequest) -> EchoResponse:
        raise AssertionError("surface bypassed the injected executor")

    class HandlerValidationExecutor:
        async def run(self, name: str, request: BaseModel):
            try:
                EchoRequest.model_validate({"text": []})
            except ValidationError as exc:
                raise exc

    app = typer.Typer()
    app.callback()(lambda: None)
    add_commands(app, OperationClient(registry, HandlerValidationExecutor()))
    runner = CliRunner()

    missing_value = runner.invoke(app, ["validate", "--input-file"])
    assert missing_value.exit_code == 2
    assert json.loads(missing_value.stdout)["success"] is False

    handler_validation = runner.invoke(
        app,
        ["validate", "--input-json", '{"text":"valid"}'],
    )
    assert handler_validation.exit_code == 4
    assert json.loads(handler_validation.stdout)["success"] is False


def test_typer_command_wraps_callback_free_app_and_composes_custom_group() -> None:
    import typer
    from typer.core import TyperGroup
    from typer.testing import CliRunner

    class CustomGroup(TyperGroup):
        pass

    client, _executor = build_client()
    app = typer.Typer(cls=CustomGroup)
    add_commands(app, client)
    command = typer.main.get_command(app)
    assert isinstance(command, CustomGroup)

    missing_value = CliRunner().invoke(app, ["echo-now", "--input-file"])
    assert missing_value.exit_code == 2
    assert json.loads(missing_value.stdout)["success"] is False


def test_typer_command_redacts_sensitive_parser_errors(monkeypatch) -> None:
    import typer
    from typer.testing import CliRunner

    secret = "SUPERSECRET"
    registry = OperationRegistry()

    @registry.operation(
        "secret",
        request_model=EchoRequest,
        response_model=EchoResponse,
        metadata={"sensitive": True},
    )
    def poison_handler(request: EchoRequest) -> EchoResponse:
        raise AssertionError("surface bypassed the injected executor")

    app = typer.Typer()
    add_commands(app, OperationClient(registry, RecordingExecutor()))
    result = CliRunner().invoke(app, ["secret", "--stdin", secret])
    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "success": False,
        "error": "invalid command input",
    }
    assert secret not in result.stdout
    direct_output = []
    import api_surface_sync.surfaces.typer as typer_surface

    monkeypatch.setattr(typer_surface, "_emit", direct_output.append)
    raised = None
    try:
        app(args=["secret", "--stdin", secret])
    except SystemExit as exc:
        raised = exc
        assert exc.code == 2
    assert direct_output == [{"success": False, "error": "invalid command input"}]
    assert secret not in json.dumps(direct_output)
    assert raised is not None
    assert raised.__cause__ is None
    assert raised.__context__ is None

    direct_output.clear()
    command = typer.main.get_command(app)
    assert command.main(
        args=["secret", "--stdin", secret],
        standalone_mode=False,
    ) == 2
    assert direct_output == [{"success": False, "error": "invalid command input"}]
    assert secret not in json.dumps(direct_output)


def test_typer_command_redaction_is_shared_across_multiple_registries() -> None:
    import typer
    from typer.testing import CliRunner

    sensitive = OperationRegistry()

    @sensitive.operation(
        "secret",
        request_model=EchoRequest,
        response_model=EchoResponse,
        metadata={"sensitive": True},
    )
    def poison_sensitive(request: EchoRequest) -> EchoResponse:
        raise AssertionError

    regular = OperationRegistry()

    @regular.operation(
        "regular",
        request_model=EchoRequest,
        response_model=EchoResponse,
    )
    def poison_regular(request: EchoRequest) -> EchoResponse:
        raise AssertionError

    app = typer.Typer()
    add_commands(app, OperationClient(sensitive, RecordingExecutor()))
    add_commands(app, OperationClient(regular, RecordingExecutor()))
    secret = "SUPERSECRET"
    result = CliRunner().invoke(app, ["regular", "--stdin", secret])
    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "success": False,
        "error": "invalid command input",
    }
    assert secret not in result.stdout


def test_typer_command_wraps_response_serialization_errors() -> None:
    import typer
    from typer.testing import CliRunner

    class AnyResponse(BaseModel):
        value: object

    registry = OperationRegistry()

    @registry.operation(
        "serialize",
        request_model=EchoRequest,
        response_model=AnyResponse,
    )
    def poison_handler(request: EchoRequest) -> AnyResponse:
        raise AssertionError("surface bypassed the injected executor")

    class UnserializableExecutor:
        async def run(self, name: str, request: BaseModel):
            return {"value": object()}

    app = typer.Typer()
    app.callback()(lambda: None)
    add_commands(app, OperationClient(registry, UnserializableExecutor()))
    result = CliRunner().invoke(
        app,
        ["serialize", "--input-json", '{"text":"valid"}'],
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["success"] is False
