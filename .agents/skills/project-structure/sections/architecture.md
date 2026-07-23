# Architecture

## Source Of Truth

`OperationRegistry` owns registration, validates public identities, and seals into an
immutable `RegistrySnapshot`. Each operation has:

- stable name
- globally unique operation ID
- Pydantic request model
- Pydantic response model
- handler
- optional summary, tags, and JSON metadata

`OperationClient` validates requests and responses around an injected
`OperationExecutor`. SDK, structured CLI, REST, and field-level MCP adapters bind to
that client and never invoke handlers directly. `LocalOperationExecutor` is the sole
in-process handler owner; HTTP and consumer-defined executors retain their own
transport and authority policy.

OpenAPI exports from the sealed snapshot and rejects ambiguous component identities
or unresolved internal references.

## Generic Boundary

The library may provide generic hooks and adapters. It must not import or encode consuming-project concepts such as TestApe flows, adapters, sessions, FS-DB, or expert-agent boundaries.
