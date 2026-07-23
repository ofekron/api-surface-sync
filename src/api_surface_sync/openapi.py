from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from pydantic import BaseModel

from api_surface_sync.registry import OperationRegistry, RegistrySnapshot

_COMPONENT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def export_openapi(
    registry: OperationRegistry | RegistrySnapshot,
    *,
    title: str,
    version: str,
    base_path: str = "",
) -> dict[str, Any]:
    snapshot = registry.snapshot() if isinstance(registry, OperationRegistry) else registry
    snapshot.assert_intact()
    allocator = _SchemaAllocator()
    paths: dict[str, Any] = {}
    normalized_base = base_path.rstrip("/")
    for item in snapshot.all():
        request_ref = allocator.register(item.request_model)
        response_ref = allocator.register(item.response_model)
        path = f"{normalized_base}/{item.name.replace('_', '-')}"
        paths[path] = {
            "post": {
                "operationId": item.operation_id,
                "summary": item.summary,
                "tags": list(item.tags),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": request_ref},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": response_ref},
                            }
                        },
                    }
                },
            }
        }
    document = {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": paths,
        "components": {"schemas": allocator.schemas},
    }
    _assert_internal_refs_resolve(document)
    return document


class _SchemaAllocator:
    def __init__(self) -> None:
        self.schemas: dict[str, Any] = {}
        self._root_models: dict[str, type[BaseModel]] = {}

    def register(self, model: type[BaseModel]) -> str:
        root_key = _safe_component_key(model.__name__)
        existing_model = self._root_models.get(root_key)
        if existing_model is not None and existing_model is not model:
            raise ValueError(
                f"OpenAPI schema name collision for {root_key!r}: distinct models"
            )
        self._root_models[root_key] = model
        schema = deepcopy(
            model.model_json_schema(ref_template="#/$defs/{model}")
        )
        definitions = schema.pop("$defs", {})
        keys = {
            definition_name: _safe_component_key(definition_name)
            for definition_name in definitions
        }
        rewritten_root = _rewrite_schema_pointers(schema, keys)
        root_pointer = f"#/components/schemas/{_escape_pointer(root_key)}"
        if rewritten_root != {"$ref": root_pointer}:
            self._add(root_key, rewritten_root)
        for definition_name, definition_schema in definitions.items():
            self._add(
                keys[definition_name],
                _rewrite_schema_pointers(definition_schema, keys),
            )
        return root_pointer

    def _add(self, key: str, schema: dict[str, Any]) -> None:
        existing = self.schemas.get(key)
        if existing is not None and existing != schema:
            raise ValueError(
                f"OpenAPI schema name collision for {key!r}: incompatible schemas"
            )
        self.schemas[key] = schema


def _safe_component_key(name: str) -> str:
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    if not key or _COMPONENT_KEY_PATTERN.fullmatch(key) is None:
        raise ValueError(f"cannot allocate OpenAPI component key for {name!r}")
    return key


def _rewrite_schema_pointers(value: Any, keys: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_schema_pointers(item, keys) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten: dict[str, Any] = {}
    for key, item in value.items():
        if key == "$ref" and isinstance(item, str):
            rewritten[key] = _rewrite_pointer(item, keys)
            continue
        if key == "mapping" and isinstance(item, dict):
            rewritten[key] = {
                mapping_key: _rewrite_pointer(pointer, keys)
                if isinstance(pointer, str)
                else pointer
                for mapping_key, pointer in item.items()
            }
            continue
        rewritten[key] = _rewrite_schema_pointers(item, keys)
    return rewritten


def _rewrite_pointer(pointer: str, keys: dict[str, str]) -> str:
    prefix = "#/$defs/"
    if not pointer.startswith(prefix):
        return pointer
    raw_name = _unescape_pointer(pointer[len(prefix) :])
    try:
        key = keys[raw_name]
    except KeyError as exc:
        raise ValueError(f"unresolved Pydantic schema reference: {pointer}") from exc
    return f"#/components/schemas/{_escape_pointer(key)}"


def _assert_internal_refs_resolve(document: dict[str, Any]) -> None:
    schemas = document["components"]["schemas"]

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                _assert_schema_pointer(item, schemas)
            elif key == "mapping" and isinstance(item, dict):
                for pointer in item.values():
                    if isinstance(pointer, str):
                        _assert_schema_pointer(pointer, schemas)
            else:
                walk(item)

    walk(document)


def _assert_schema_pointer(pointer: str, schemas: dict[str, Any]) -> None:
    prefix = "#/components/schemas/"
    if not pointer.startswith(prefix):
        return
    key = _unescape_pointer(pointer[len(prefix) :])
    if key not in schemas:
        raise ValueError(f"unresolved OpenAPI schema reference: {pointer}")


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _unescape_pointer(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")
