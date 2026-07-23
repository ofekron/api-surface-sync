from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field, create_model

from api_surface_sync import OperationRegistry, export_openapi


class Cat(BaseModel):
    kind: Literal["cat"]
    lives: int


class Dog(BaseModel):
    kind: Literal["dog"]
    good: bool


class PetRequest(BaseModel):
    pet: Annotated[Cat | Dog, Field(discriminator="kind")]


class PetResponse(BaseModel):
    accepted: bool


def build_registry() -> OperationRegistry:
    registry = OperationRegistry()

    @registry.operation(
        "create_pet",
        operation_id="pets.create",
        request_model=PetRequest,
        response_model=PetResponse,
        summary="Create a pet.",
        tags=("pets",),
    )
    def create_pet(request: PetRequest) -> PetResponse:
        return PetResponse(accepted=True)

    return registry


def test_export_openapi_contains_shared_identity_and_resolved_graph() -> None:
    spec = export_openapi(
        build_registry(),
        title="Example API",
        version="1.2.3",
        base_path="/api",
    )
    operation = spec["paths"]["/api/create-pet"]["post"]
    assert operation["operationId"] == "pets.create"
    assert operation["tags"] == ["pets"]
    assert spec["info"] == {"title": "Example API", "version": "1.2.3"}
    mappings = [
        value
        for schema in spec["components"]["schemas"].values()
        for value in _discriminator_mappings(schema)
    ]
    assert mappings
    for pointer in _all_schema_pointers(spec):
        key = pointer.removeprefix("#/components/schemas/").replace("~1", "/").replace(
            "~0", "~"
        )
        assert key in spec["components"]["schemas"]


def test_export_openapi_sanitizes_generic_model_component_name() -> None:
    Unsafe = create_model("Page[int]", value=(int, ...))
    registry = OperationRegistry()

    @registry.operation("page", request_model=Unsafe, response_model=PetResponse)
    def page(request):
        return PetResponse(accepted=True)

    spec = export_openapi(registry, title="Pages", version="1")
    assert "Page_int" in spec["components"]["schemas"]


def test_export_openapi_raises_on_sanitized_schema_collision() -> None:
    First = create_model("A/B", a=(str, ...))
    Second = create_model("A B", b=(int, ...))
    registry = OperationRegistry()

    @registry.operation("collide", request_model=First, response_model=Second)
    def collide(request):
        return Second(b=1)

    with pytest.raises(ValueError, match="collision"):
        export_openapi(registry, title="Collide", version="1")


def test_export_openapi_rejects_distinct_equal_schema_identities() -> None:
    First = create_model("Duplicate", value=(int, ...))
    Second = create_model("Duplicate", value=(int, ...))
    registry = OperationRegistry()

    @registry.operation("collide", request_model=First, response_model=Second)
    def collide(request):
        return Second(value=request.value)

    with pytest.raises(ValueError, match="distinct models"):
        export_openapi(registry, title="Collide", version="1")


def _all_schema_pointers(value):
    if isinstance(value, list):
        for item in value:
            yield from _all_schema_pointers(item)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key == "$ref" and isinstance(item, str):
            yield item
        elif key == "mapping" and isinstance(item, dict):
            yield from (pointer for pointer in item.values() if isinstance(pointer, str))
        else:
            yield from _all_schema_pointers(item)


def _discriminator_mappings(value):
    if isinstance(value, list):
        for item in value:
            yield from _discriminator_mappings(item)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key == "discriminator" and isinstance(item, dict) and "mapping" in item:
            yield item["mapping"]
        else:
            yield from _discriminator_mappings(item)
