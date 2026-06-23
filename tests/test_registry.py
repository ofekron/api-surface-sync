import asyncio

from pydantic import BaseModel

from api_surface_sync import OperationClient, OperationRegistry


class EchoRequest(BaseModel):
    text: str


class EchoResponse(BaseModel):
    text: str


def test_operation_client_runs_registered_operation() -> None:
    registry = OperationRegistry()

    @registry.operation(
        "echo",
        request_model=EchoRequest,
        response_model=EchoResponse,
        summary="Return the input text.",
    )
    def echo(request: EchoRequest) -> EchoResponse:
        return EchoResponse(text=request.text)

    client = OperationClient(registry)
    result = asyncio.run(client.run("echo", {"text": "hello"}))

    assert result == EchoResponse(text="hello")


def test_registry_schema_exposes_contracts() -> None:
    registry = OperationRegistry()

    @registry.operation("echo", request_model=EchoRequest, response_model=EchoResponse)
    def echo(request: EchoRequest) -> EchoResponse:
        return EchoResponse(text=request.text)

    schema = registry.schema()

    assert schema["operations"]["echo"]["request"]["properties"]["text"]["type"] == "string"
    assert schema["operations"]["echo"]["response"]["properties"]["text"]["type"] == "string"
