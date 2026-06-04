# Skill: builder_python

## Purpose
Generate a Python script (for a Text DAT) that creates a TouchDesigner network inside a given parent COMP.

This is the "in-editor build" path: no file-format edits required; useful for rapid iteration and debugging.

## Inputs
- `TDNetworkSpec` (required): nodes, connections, parameters, optional layout hints.
- `Target` (required):
  - `parent_path`: e.g. `/project1/myComp`
  - `clean`: whether to delete existing children first (safe mode recommended: create inside a named container)
- `Constraints` (optional):
  - naming: stable node names, collision policy (`reuse|rename|delete`)
  - operator availability (TD version)

## Outputs
- `TDTextDatScript` (required):
  - python source code that:
    - creates nodes with correct types
    - sets parameters (only valid pars)
    - wires connections
    - optionally positions nodes
  - includes a small "how to run" header (comment only)

## Hard rules
- Script must be runnable in TouchDesigner without external dependencies.
- Must not invent parameter names; if uncertain, omit and mark as TODO in the *output metadata* (not in code comments unless requested).
- Must be idempotent or follow a predictable collision policy.

## Recommended approach
1) Create/get a dedicated container COMP as build root.
2) Create all nodes first.
3) Set parameters after creation.
4) Wire connections after parameters (some nodes validate input counts).
5) Apply layout last.

