from __future__ import annotations

from typing import Any

from api_surface_sync.registry import OperationRegistry


class OperationClient:
    def __init__(self, registry: OperationRegistry) -> None:
        self._registry = registry

    async def run(self, name: str, payload: dict[str, Any]) -> Any:
        result = await self._registry.get(name).run(payload)
        return result.value

    def schema(self) -> dict[str, Any]:
        return self._registry.schema()

