from __future__ import annotations

from typing import Any
from urllib import request as urllib_request
import json

from api_surface_sync.registry import OperationRegistry


class OperationClient:
    def __init__(self, registry: OperationRegistry) -> None:
        self._registry = registry

    async def run(self, name: str, payload: dict[str, Any]) -> Any:
        result = await self._registry.get(name).run(payload)
        return result.value

    def schema(self) -> dict[str, Any]:
        return self._registry.schema()


class HttpOperationClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def run(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            f"{self._base_url}/{name.replace('_', '-')}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
