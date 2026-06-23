# Architecture

## Source Of Truth

`OperationRegistry` owns the public operation list. Each operation has:

- stable name
- Pydantic request model
- Pydantic response model
- handler
- optional summary

Surfaces bind to registered operations and must not reimplement business logic.

## Generic Boundary

The library may provide generic hooks and adapters. It must not import or encode consuming-project concepts such as TestApe flows, adapters, sessions, FS-DB, or expert-agent boundaries.

