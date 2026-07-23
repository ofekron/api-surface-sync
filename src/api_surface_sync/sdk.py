from __future__ import annotations

import asyncio
from collections.abc import Awaitable
import inspect
import json
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel

from api_surface_sync.registry import OperationRegistry, RegistrySnapshot


class OperationExecutor(Protocol):
    async def run(self, name: str, request: BaseModel) -> Any: ...


class OperationTransportError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OperationClient:
    def __init__(
        self,
        registry: OperationRegistry | RegistrySnapshot,
        executor: OperationExecutor,
    ) -> None:
        self._snapshot = (
            registry.snapshot() if isinstance(registry, OperationRegistry) else registry
        )
        self._executor = executor

    @property
    def snapshot(self) -> RegistrySnapshot:
        self._snapshot.assert_intact()
        return self._snapshot

    @property
    def operation_names(self) -> tuple[str, ...]:
        return self.snapshot.names()

    async def run(self, name: str, payload: BaseModel | dict[str, Any]) -> BaseModel:
        operation = self.snapshot.get(name)
        request = _validate_model(operation.request_model, payload)
        raw_response = await self._executor.run(name, request)
        return _validate_model(operation.response_model, raw_response)

    def schema(self) -> dict[str, Any]:
        return self.snapshot.schema()


class LocalOperationExecutor:
    def __init__(self, registry: OperationRegistry | RegistrySnapshot) -> None:
        self._snapshot = (
            registry.snapshot() if isinstance(registry, OperationRegistry) else registry
        )

    async def run(self, name: str, request: BaseModel) -> Any:
        operation = self._snapshot.get(name)
        if inspect.iscoroutinefunction(operation.handler):
            return await operation.handler(request)
        result = await asyncio.to_thread(operation.handler, request)
        if inspect.isawaitable(result):
            return await _await_result(result)
        return result


class HttpOperationExecutor:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def run(self, name: str, request: BaseModel) -> Any:
        return await asyncio.to_thread(self._post, name, request)

    def _post(self, name: str, payload: BaseModel) -> Any:
        body = json.dumps(
            payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ).encode("utf-8")
        http_request = urllib_request.Request(
            f"{self._base_url}/{name.replace('_', '-')}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(http_request, timeout=self._timeout) as response:
                status = response.status
                content_type = response.headers.get_content_type()
                data = response.read()
        except urllib_error.HTTPError as exc:
            raise OperationTransportError(
                f"operation HTTP request failed with status {exc.code}",
                status=exc.code,
            ) from exc
        except urllib_error.URLError as exc:
            raise OperationTransportError("operation HTTP request failed") from exc
        if not 200 <= status < 300:
            raise OperationTransportError(
                f"operation HTTP request failed with status {status}",
                status=status,
            )
        if content_type != "application/json":
            raise OperationTransportError(
                f"operation HTTP response has unsupported content type {content_type!r}",
                status=status,
            )
        try:
            return json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OperationTransportError(
                "operation HTTP response is not valid JSON",
                status=status,
            ) from exc


class HttpOperationClient(OperationClient):
    def __init__(
        self,
        registry: OperationRegistry | RegistrySnapshot,
        base_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            registry,
            HttpOperationExecutor(base_url, timeout=timeout),
        )


def local_client(registry: OperationRegistry) -> OperationClient:
    snapshot = registry.snapshot()
    return OperationClient(snapshot, LocalOperationExecutor(snapshot))


def _validate_model(
    model: type[BaseModel],
    value: BaseModel | dict[str, Any] | Any,
) -> BaseModel:
    if isinstance(value, BaseModel):
        value = value.model_dump(
            mode="python",
            by_alias=True,
            round_trip=True,
            exclude_unset=True,
        )
    return model.model_validate(value)


async def _await_result(result: Awaitable[Any]) -> Any:
    return await result
