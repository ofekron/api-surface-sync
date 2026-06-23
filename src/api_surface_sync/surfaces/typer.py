from __future__ import annotations

import asyncio
import json
from typing import Any

from api_surface_sync.registry import OperationRegistry


def add_commands(app: Any, registry: OperationRegistry) -> None:
    for item in registry.all():
        command_name = item.name.replace("_", "-")

        def command(payload_json: str, operation=item) -> None:
            payload = json.loads(payload_json)
            result = asyncio.run(operation.run(payload))
            print(result.value.model_dump_json())

        command.__name__ = item.name
        command.__doc__ = item.summary
        app.command(name=command_name)(command)

