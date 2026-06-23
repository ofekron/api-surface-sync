from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)
Handler = Callable[[Any], Any | Awaitable[Any]]


@dataclass(frozen=True)
class OperationResult(Generic[ResponseT]):
    value: ResponseT


@dataclass(frozen=True)
class Operation(Generic[RequestT, ResponseT]):
    name: str
    summary: str
    request_model: type[RequestT]
    response_model: type[ResponseT]
    handler: Handler
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    async def run(self, payload: RequestT | dict[str, Any]) -> OperationResult[ResponseT]:
        request = self.request_model.model_validate(payload)
        raw_result = self.handler(request)
        if isawaitable(raw_result):
            raw_result = await raw_result
        return OperationResult(self.response_model.model_validate(raw_result))

    def request_schema(self) -> dict[str, Any]:
        return self.request_model.model_json_schema()

    def response_schema(self) -> dict[str, Any]:
        return self.response_model.model_json_schema()


class OperationRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, Operation[Any, Any]] = {}

    def register(self, item: Operation[Any, Any]) -> Operation[Any, Any]:
        if item.name in self._operations:
            raise ValueError(f"operation already registered: {item.name}")
        self._operations[item.name] = item
        return item

    def operation(
        self,
        name: str,
        *,
        request_model: type[RequestT],
        response_model: type[ResponseT],
        summary: str = "",
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.register(
                Operation(
                    name=name,
                    summary=summary,
                    request_model=request_model,
                    response_model=response_model,
                    handler=handler,
                    tags=tags,
                    metadata=metadata or {},
                )
            )
            return handler

        return decorator

    def get(self, name: str) -> Operation[Any, Any]:
        try:
            return self._operations[name]
        except KeyError as exc:
            raise KeyError(f"unknown operation: {name}") from exc

    def all(self) -> tuple[Operation[Any, Any], ...]:
        return tuple(self._operations.values())

    def schema(self) -> dict[str, Any]:
        return {
            "operations": {
                item.name: {
                    "summary": item.summary,
                    "tags": list(item.tags),
                    "metadata": item.metadata,
                    "request": item.request_schema(),
                    "response": item.response_schema(),
                }
                for item in self.all()
            }
        }


def operation(
    registry: OperationRegistry,
    name: str,
    *,
    request_model: type[RequestT],
    response_model: type[ResponseT],
    summary: str = "",
    tags: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> Callable[[Handler], Handler]:
    return registry.operation(
        name,
        request_model=request_model,
        response_model=response_model,
        summary=summary,
        tags=tags,
        metadata=metadata,
    )
