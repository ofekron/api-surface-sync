from pydantic import BaseModel

from api_surface_sync import OperationRegistry
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools


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


def test_mcp_tools_are_registered_from_registry() -> None:
    registry = OperationRegistry()

    @registry.operation("ping", request_model=PingRequest, response_model=PingResponse)
    def ping(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    server = FakeMcpServer()
    add_tools(server, registry)

    assert [tool.__name__ for tool in server.tools] == ["ping"]


def test_fastapi_routes_are_registered_from_registry() -> None:
    from fastapi import FastAPI

    registry = OperationRegistry()

    @registry.operation("ping", request_model=PingRequest, response_model=PingResponse)
    def ping(request: PingRequest) -> PingResponse:
        return PingResponse(value=request.value)

    app = FastAPI()
    add_routes(app, registry, prefix="/api")

    assert any(route.path == "/api/ping" for route in app.routes)
