import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest
from pydantic import BaseModel, Field, ValidationError

from api_surface_sync import (
    HttpOperationClient,
    OperationClient,
    OperationRegistry,
    OperationTransportError,
    export_openapi,
)
from api_surface_sync.surfaces.fastapi import add_routes
from api_surface_sync.surfaces.mcp import add_tools
from api_surface_sync.surfaces.typer import add_commands


class Request(BaseModel):
    value: str = Field(alias="wire_value")
    optional: str | None = None


class Response(BaseModel):
    echoed: str


def build_registry() -> OperationRegistry:
    registry = OperationRegistry()

    @registry.operation(
        "echo",
        operation_id="echo.run",
        request_model=Request,
        response_model=Response,
    )
    def echo(request: Request) -> Response:
        raise AssertionError("transport client accessed local handler")

    return registry


class RecordingExecutor:
    async def run(self, name: str, request: BaseModel):
        return {"echoed": request.value}


def test_every_surface_uses_one_exact_snapshot_census() -> None:
    registry = build_registry()
    client = OperationClient(registry, RecordingExecutor())

    class Mcp:
        def __init__(self):
            self.tools = []

        def tool(self):
            return lambda func: self.tools.append(func) or func

    class Typer:
        def __init__(self):
            self.commands = []

        def command(self, *, name):
            return lambda func: self.commands.append((name, func)) or func

    mcp = Mcp()
    typer = Typer()
    add_tools(mcp, client)
    add_commands(typer, client)
    from fastapi import FastAPI

    app = FastAPI()
    add_routes(app, client)
    spec = export_openapi(registry.snapshot(), title="Parity", version="1")
    assert client.operation_names == ("echo",)
    assert [tool.__name__ for tool in mcp.tools] == ["echo"]
    assert [name for name, _ in typer.commands] == ["echo"]
    assert {route.path for route in app.routes if route.path == "/echo"} == {"/echo"}
    assert set(spec["paths"]) == {"/echo"}
    assert spec["paths"]["/echo"]["post"]["operationId"] == "echo.run"


def test_mcp_schema_matches_canonical_request_fields() -> None:
    from mcp.server.fastmcp import FastMCP

    registry = build_registry()
    server = FastMCP("parity")
    add_tools(server, OperationClient(registry, RecordingExecutor()))
    tool = asyncio.run(server.list_tools())[0]
    request_schema = registry.schema()["operations"]["echo"]["request"]

    assert tool.inputSchema["properties"] == request_schema["properties"]
    assert tool.inputSchema["required"] == request_schema["required"]
    assert "payload" not in tool.inputSchema["properties"]


def test_http_client_preserves_omission_and_explicit_null() -> None:
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            received.append(payload)
            body = json.dumps({"echoed": payload["wire_value"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        client = HttpOperationClient(
            build_registry(),
            f"http://127.0.0.1:{server.server_port}",
        )
        assert asyncio.run(client.run("echo", {"wire_value": "one"})) == Response(
            echoed="one"
        )
        assert asyncio.run(
            client.run("echo", {"wire_value": "two", "optional": None})
        ) == Response(echoed="two")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert received == [
        {"wire_value": "one"},
        {"wire_value": "two", "optional": None},
    ]


def test_http_client_rejects_error_content_and_invalid_response() -> None:
    registry = build_registry()

    class Executor:
        async def run(self, name, request):
            return {"wrong": "shape"}

    with pytest.raises(ValidationError):
        asyncio.run(OperationClient(registry, Executor()).run("echo", {"wire_value": "x"}))

    error = OperationTransportError("failed", status=503)
    assert error.status == 503


@pytest.mark.parametrize(
    ("status", "content_type", "body", "match"),
    [
        (503, "application/json", b'{"error":"unavailable"}', "status 503"),
        (200, "text/plain", b"plain", "content type"),
        (200, "application/json", b"{", "valid JSON"),
    ],
)
def test_http_client_rejects_transport_protocol_violations(
    status: int,
    content_type: str,
    body: bytes,
    match: str,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        client = HttpOperationClient(
            build_registry(),
            f"http://127.0.0.1:{server.server_port}",
        )
        with pytest.raises(OperationTransportError, match=match):
            asyncio.run(client.run("echo", {"wire_value": "x"}))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_registry_rejects_divergent_alias_domains() -> None:
    class Divergent(BaseModel):
        value: str = Field(
            alias="alias",
            validation_alias="input",
            serialization_alias="output",
        )

    registry = OperationRegistry()
    with pytest.raises(ValueError, match="divergent aliases"):

        @registry.operation("bad", request_model=Divergent, response_model=Response)
        def bad(request):
            return Response(echoed="")
