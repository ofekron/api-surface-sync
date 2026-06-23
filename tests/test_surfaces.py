import asyncio
import inspect

from pydantic import BaseModel

from api_surface_sync import OperationRegistry
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools
from api_surface_sync.surfaces.typer import add_commands


class PingRequest(BaseModel):
    value: str


class OptionalPingRequest(BaseModel):
    value: str
    excited: bool = False


class PingResponse(BaseModel):
    value: str


class FakeMcpServer:
    def __init__(self) -> None:
        self.tools = []

    def tool(self):
        def decorator(func):
            self.tools.append(func)
            return func

        return decorator


class FakeTyperApp:
    def __init__(self) -> None:
        self.commands = []

    def command(self, *, name):
        def decorator(func):
            self.commands.append((name, func))
            return func

        return decorator


def test_typer_commands_use_request_model_fields() -> None:
    registry = OperationRegistry()

    @registry.operation("ping_now", request_model=OptionalPingRequest, response_model=PingResponse)
    def ping_now(request: OptionalPingRequest) -> PingResponse:
        suffix = "!" if request.excited else ""
        return PingResponse(value=f"{request.value}{suffix}")

    app = FakeTyperApp()
    add_commands(app, registry)

    assert app.commands[0][0] == "ping-now"
    signature = inspect.signature(app.commands[0][1])
    assert list(signature.parameters) == ["value", "excited"]
    assert signature.parameters["value"].annotation is str
    assert signature.parameters["value"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["excited"].annotation is bool
    assert signature.parameters["excited"].kind is inspect.Parameter.KEYWORD_ONLY


def test_typer_command_runs_with_generated_arguments_and_options() -> None:
    import typer
    from typer.testing import CliRunner

    registry = OperationRegistry()

    @registry.operation("ping_now", request_model=OptionalPingRequest, response_model=PingResponse)
    def ping_now(request: OptionalPingRequest) -> PingResponse:
        suffix = "!" if request.excited else ""
        return PingResponse(value=f"{request.value}{suffix}")

    @registry.operation("echo", request_model=PingRequest, response_model=PingResponse)
    def echo(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    app = typer.Typer()
    add_commands(app, registry)

    result = CliRunner().invoke(app, ["ping-now", "hello", "--excited"])

    assert result.exit_code == 0
    assert result.stdout.strip() == '{"value":"hello!"}'


def test_mcp_tools_are_registered_from_registry() -> None:
    registry = OperationRegistry()

    @registry.operation("ping", request_model=PingRequest, response_model=PingResponse)
    def ping(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    server = FakeMcpServer()
    public_tools = {}
    add_tools(server, registry, tool_registry=public_tools)

    assert [tool.__name__ for tool in server.tools] == ["ping"]
    assert set(public_tools) == {"ping"}
    signature = inspect.signature(server.tools[0])
    assert list(signature.parameters) == ["value"]
    assert signature.parameters["value"].annotation is str
    assert signature.return_annotation is PingResponse
    assert asyncio.run(public_tools["ping"](value="pong")) == {"value": "pong"}


def test_fastapi_routes_are_registered_from_registry() -> None:
    from fastapi import FastAPI

    registry = OperationRegistry()

    @registry.operation("ping", request_model=PingRequest, response_model=PingResponse)
    def ping(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    app = FastAPI()
    add_routes(app, registry, prefix="/api")

    assert any(route.path == "/api/ping" for route in app.routes)


def test_fastapi_route_keeps_prefix_underscores_and_normalizes_operation_name() -> None:
    from fastapi import FastAPI

    registry = OperationRegistry()

    @registry.operation("ping_now", request_model=PingRequest, response_model=PingResponse)
    def ping_now(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    app = FastAPI()
    add_routes(app, registry, prefix="/internal_api/")

    assert any(route.path == "/internal_api/ping-now" for route in app.routes)
