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
    assert json.loads(json_result.stdout) == {"value": "json!"}
    input_path = tmp_path / "request.json"
    input_path.write_text('{"text":"file","suffix":"?"}', encoding="utf-8")
    file_result = runner.invoke(
        app,
        ["echo-now", "--input-file", str(input_path)],
    )
    assert file_result.exit_code == 0
    assert json.loads(file_result.stdout) == {"value": "file?"}
    stdin_result = runner.invoke(
        app,
        ["echo-now", "--stdin"],
        input='{"text":"stdin","suffix":null}',
    )
    assert stdin_result.exit_code != 0
    missing_result = runner.invoke(app, ["echo-now"])
    assert missing_result.exit_code != 0
    assert executor.calls == [
        ("echo_now", {"text": "json"}),
        ("echo_now", {"text": "file", "suffix": "?"}),
    ]
