import asyncio
import time

import pytest
from pydantic import BaseModel

from api_surface_sync import (
    LocalOperationExecutor,
    Operation,
    OperationClient,
    OperationContractError,
    OperationRegistry,
    local_client,
)


class EchoRequest(BaseModel):
    text: str


class EchoResponse(BaseModel):
    text: str


def test_local_client_runs_sync_handler_without_blocking_event_loop() -> None:
    registry = OperationRegistry()

    @registry.operation("echo", request_model=EchoRequest, response_model=EchoResponse)
    def echo(request: EchoRequest) -> EchoResponse:
        time.sleep(0.05)
        return EchoResponse(text=request.text)

    async def scenario() -> None:
        task = asyncio.create_task(local_client(registry).run("echo", {"text": "hello"}))
        await asyncio.sleep(0.005)
        assert not task.done()
        assert await task == EchoResponse(text="hello")

    asyncio.run(scenario())


def test_local_executor_awaits_awaitable_returned_by_sync_handler() -> None:
    registry = OperationRegistry()

    @registry.operation("echo", request_model=EchoRequest, response_model=EchoResponse)
    def echo(request: EchoRequest):
        async def finish() -> EchoResponse:
            return EchoResponse(text=request.text)

        return finish()

    assert asyncio.run(local_client(registry).run("echo", {"text": "hello"})) == EchoResponse(
        text="hello"
    )


def test_client_revalidates_constructed_request_and_mutated_response() -> None:
    registry = OperationRegistry()
    reached_executor = False

    @registry.operation("echo", request_model=EchoRequest, response_model=EchoResponse)
    def echo(request: EchoRequest) -> EchoResponse:
        return EchoResponse(text=request.text)

    class Executor:
        async def run(self, name: str, request: BaseModel):
            nonlocal reached_executor
            reached_executor = True
            response = EchoResponse(text="valid")
            response.__dict__["text"] = 3
            return response

    client = OperationClient(registry, Executor())
    with pytest.raises(OperationContractError, match="request validation failed"):
        asyncio.run(client.run("echo", EchoRequest.model_construct()))
    assert not reached_executor
    with pytest.raises(OperationContractError, match="response validation failed"):
        asyncio.run(client.run("echo", {"text": "valid"}))


def test_registry_seals_identity_metadata_and_model_contracts() -> None:
    registry = OperationRegistry()
    metadata = {"nested": {"values": ["a"]}}
    registry.register(
        Operation(
            name="echo",
            operation_id="echo.v1",
            summary="",
            request_model=EchoRequest,
            response_model=EchoResponse,
            handler=lambda request: request,
            metadata=metadata,
        )
    )
    snapshot = registry.snapshot()
    metadata["nested"]["values"].append("b")
    assert snapshot.schema()["operations"]["echo"]["metadata"] == {
        "nested": {"values": ["a"]}
    }
    with pytest.raises(RuntimeError, match="sealed"):
        registry.register(
            Operation(
                name="other",
                operation_id="other",
                summary="",
                request_model=EchoRequest,
                response_model=EchoResponse,
                handler=lambda request: request,
            )
        )
    original_title = EchoRequest.model_config.get("title")
    try:
        EchoRequest.model_config["title"] = "Mutated"
        with pytest.raises(RuntimeError, match="changed after snapshot"):
            snapshot.schema()
    finally:
        if original_title is None:
            EchoRequest.model_config.pop("title", None)
        else:
            EchoRequest.model_config["title"] = original_title


@pytest.mark.parametrize("name", ["../escape", "two--parts", "Upper", "has-hyphen"])
def test_registry_rejects_unsafe_operation_names(name: str) -> None:
    registry = OperationRegistry()
    with pytest.raises(ValueError, match="operation name"):
        registry.register(
            Operation(
                name=name,
                operation_id="safe",
                summary="",
                request_model=EchoRequest,
                response_model=EchoResponse,
                handler=lambda request: request,
            )
        )


def test_registry_rejects_duplicate_operation_ids() -> None:
    registry = OperationRegistry()
    for name in ("first", "second"):
        item = Operation(
            name=name,
            operation_id="shared",
            summary="",
            request_model=EchoRequest,
            response_model=EchoResponse,
            handler=lambda request: request,
        )
        if name == "first":
            registry.register(item)
        else:
            with pytest.raises(ValueError, match="operation_id"):
                registry.register(item)
