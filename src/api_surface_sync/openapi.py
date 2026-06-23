from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from api_surface_sync.registry import OperationRegistry


def export_openapi(
    registry: OperationRegistry,
    *,
    title: str,
    version: str = "0.1.0",
    base_path: str = "",
) -> dict[str, Any]:
    components: dict[str, Any] = {"schemas": {}}
    paths: dict[str, Any] = {}

    normalized_base = base_path.rstrip("/")
    for item in registry.all():
        request_ref = _register_schema(components, item.request_model)
        response_ref = _register_schema(components, item.response_model)
        path = f"{normalized_base}/{item.name.replace('_', '-')}"
        operation_id = item.metadata.get("operation_id") or item.name
        paths[path] = {
            "post": {
                "operationId": operation_id,
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

    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": paths,
        "components": components,
    }


def _register_schema(components: dict[str, Any], model: type[BaseModel]) -> str:
    name = model.__name__
    schema = deepcopy(model.model_json_schema(ref_template="#/components/schemas/{model}"))
    definitions = schema.pop("$defs", {})
    components["schemas"].setdefault(name, schema)
    for definition_name, definition_schema in definitions.items():
        components["schemas"].setdefault(definition_name, definition_schema)
    return f"#/components/schemas/{name}"
