from pydantic import BaseModel

from api_surface_sync import OperationRegistry, export_openapi


class CreateRequest(BaseModel):
    name: str


class CreateResponse(BaseModel):
    id: str
    name: str


def test_export_openapi_contains_operation_contracts() -> None:
    registry = OperationRegistry()

    @registry.operation(
        "create_item",
        request_model=CreateRequest,
        response_model=CreateResponse,
        summary="Create an item.",
        tags=("items",),
    )
    def create_item(request: CreateRequest) -> CreateResponse:
        return CreateResponse(id="item-1", name=request.name)

    spec = export_openapi(registry, title="Example API", version="1.2.3", base_path="/api")

    operation = spec["paths"]["/api/create-item"]["post"]
    assert spec["openapi"] == "3.1.0"
    assert spec["info"] == {"title": "Example API", "version": "1.2.3"}
    assert operation["operationId"] == "create_item"
    assert operation["tags"] == ["items"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateResponse"
    }
    assert spec["components"]["schemas"]["CreateRequest"]["properties"]["name"]["type"] == "string"


def test_registry_schema_includes_tags_and_metadata() -> None:
    registry = OperationRegistry()

    @registry.operation(
        "create_item",
        request_model=CreateRequest,
        response_model=CreateResponse,
        summary="Create an item.",
        tags=("items",),
        metadata={"visibility": "public"},
    )
    def create_item(request: CreateRequest) -> CreateResponse:
        return CreateResponse(id="item-1", name=request.name)

    operation = registry.schema()["operations"]["create_item"]

    assert operation["tags"] == ["items"]
    assert operation["metadata"] == {"visibility": "public"}
