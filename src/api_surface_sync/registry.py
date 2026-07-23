from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
import keyword
import re
from types import MappingProxyType
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)
Handler = Callable[[Any], Any]

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_OPERATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


@dataclass(frozen=True)
class Operation(Generic[RequestT, ResponseT]):
    name: str
    operation_id: str
    summary: str
    request_model: type[RequestT]
    response_model: type[ResponseT]
    handler: Handler
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = MappingProxyType({})

    def request_schema(self) -> dict[str, Any]:
        return self.request_model.model_json_schema()

    def response_schema(self) -> dict[str, Any]:
        return self.response_model.model_json_schema()


@dataclass(frozen=True)
class RegistrySnapshot:
    operations: tuple[Operation[Any, Any], ...]
    _by_name: Mapping[str, Operation[Any, Any]]
    _model_fingerprints: Mapping[type[BaseModel], str]

    def get(self, name: str) -> Operation[Any, Any]:
        self.assert_intact()
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown operation: {name}") from exc

    def all(self) -> tuple[Operation[Any, Any], ...]:
        self.assert_intact()
        return self.operations

    def names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.all())

    def schema(self) -> dict[str, Any]:
        return {
            "operations": {
                item.name: {
                    "operation_id": item.operation_id,
                    "summary": item.summary,
                    "tags": list(item.tags),
                    "metadata": _thaw(item.metadata),
                    "request": item.request_schema(),
                    "response": item.response_schema(),
                }
                for item in self.all()
            }
        }

    def assert_intact(self) -> None:
        for model, expected in self._model_fingerprints.items():
            if _model_fingerprint(model) != expected:
                raise RuntimeError(
                    f"registered model contract changed after snapshot: {model.__name__}"
                )


class OperationRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, Operation[Any, Any]] = {}
        self._operation_ids: set[str] = set()
        self._snapshot: RegistrySnapshot | None = None

    def register(self, item: Operation[Any, Any]) -> Operation[Any, Any]:
        if self._snapshot is not None:
            raise RuntimeError("registry is sealed")
        _validate_operation_identity(item.name, item.operation_id)
        if item.name in self._operations:
            raise ValueError(f"operation already registered: {item.name}")
        if item.operation_id in self._operation_ids:
            raise ValueError(f"operation_id already registered: {item.operation_id}")
        _validate_model_aliases(item.request_model)
        _validate_model_aliases(item.response_model)
        frozen_item = Operation(
            name=item.name,
            operation_id=item.operation_id,
            summary=item.summary,
            request_model=item.request_model,
            response_model=item.response_model,
            handler=item.handler,
            tags=tuple(item.tags),
            metadata=_freeze(deepcopy(dict(item.metadata))),
        )
        self._operations[item.name] = frozen_item
        self._operation_ids.add(item.operation_id)
        return frozen_item

    def operation(
        self,
        name: str,
        *,
        request_model: type[RequestT],
        response_model: type[ResponseT],
        operation_id: str | None = None,
        summary: str = "",
        tags: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.register(
                Operation(
                    name=name,
                    operation_id=operation_id or name,
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

    def snapshot(self) -> RegistrySnapshot:
        if self._snapshot is None:
            operations = tuple(self._operations.values())
            models = {
                model
                for item in operations
                for model in (item.request_model, item.response_model)
            }
            self._snapshot = RegistrySnapshot(
                operations=operations,
                _by_name=MappingProxyType(dict(self._operations)),
                _model_fingerprints=MappingProxyType(
                    {model: _model_fingerprint(model) for model in models}
                ),
            )
        self._snapshot.assert_intact()
        return self._snapshot

    def get(self, name: str) -> Operation[Any, Any]:
        return self.snapshot().get(name)

    def all(self) -> tuple[Operation[Any, Any], ...]:
        return self.snapshot().all()

    def schema(self) -> dict[str, Any]:
        return self.snapshot().schema()


def operation(
    registry: OperationRegistry,
    name: str,
    *,
    request_model: type[RequestT],
    response_model: type[ResponseT],
    operation_id: str | None = None,
    summary: str = "",
    tags: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> Callable[[Handler], Handler]:
    return registry.operation(
        name,
        request_model=request_model,
        response_model=response_model,
        operation_id=operation_id,
        summary=summary,
        tags=tags,
        metadata=metadata,
    )


def _validate_operation_identity(name: str, operation_id: str) -> None:
    if _NAME_PATTERN.fullmatch(name) is None:
        raise ValueError(f"invalid operation name: {name!r}")
    if _OPERATION_ID_PATTERN.fullmatch(operation_id) is None:
        raise ValueError(f"invalid operation_id: {operation_id!r}")


def _validate_model_aliases(model: type[BaseModel]) -> None:
    wire_names: set[str] = set()
    for field_name, field in model.model_fields.items():
        configured = [
            alias
            for alias in (field.alias, field.validation_alias, field.serialization_alias)
            if alias is not None
        ]
        if any(not isinstance(alias, str) for alias in configured):
            raise ValueError(f"{model.__name__}.{field_name} uses a non-string alias")
        aliases = set(configured)
        if len(aliases) > 1:
            raise ValueError(f"{model.__name__}.{field_name} uses divergent aliases")
        wire_name = configured[0] if configured else field_name
        if not wire_name.isidentifier() or keyword.iskeyword(wire_name):
            raise ValueError(f"{model.__name__}.{field_name} has invalid alias {wire_name!r}")
        if wire_name in wire_names:
            raise ValueError(f"{model.__name__} has duplicate alias {wire_name!r}")
        wire_names.add(wire_name)


def _model_fingerprint(model: type[BaseModel]) -> str:
    payload = {
        "schema": model.model_json_schema(),
        "config": sorted(
            (str(key), repr(value)) for key, value in dict(model.model_config).items()
        ),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError(f"operation metadata must contain JSON-compatible values: {value!r}")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)
