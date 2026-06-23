import inspect

from pydantic import BaseModel

from api_surface_sync import OperationRegistry
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools
from api_surface_sync.surfaces.typer import add_commands


class PingRequest(BaseModel):
    value: str


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


def test_typer_commands_hide_internal_operation_binding() -> None:
    registry = OperationRegistry()

    @registry.operation("ping_now", request_model=PingRequest, response_model=PingResponse)
    def ping_now(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    app = FakeTyperApp()
    add_commands(app, registry)

    assert app.commands[0][0] == "ping-now"
    signature = inspect.signature(app.commands[0][1])
    assert list(signature.parameters) == ["payload_json"]
    assert signature.parameters["payload_json"].annotation is str


def test_mcp_tools_are_registered_from_registry() -> None:
    registry = OperationRegistry()

    @registry.operation("ping", request_model=PingRequest, response_model=PingResponse)
    def ping(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    server = FakeMcpServer()
    add_tools(server, registry)

    assert [tool.__name__ for tool in server.tools] == ["ping"]
    signature = inspect.signature(server.tools[0])
    assert signature.parameters["payload"].annotation is PingRequest
    assert signature.return_annotation is PingResponse


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
