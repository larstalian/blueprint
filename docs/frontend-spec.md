# Frontend Integration Spec

This repo now has the backend contract the frontend needs.

The frontend must be a typed editor over `.arch/`.
It is not a drawing tool that invents architecture and asks the backend to guess later.

## Source of truth

- `.arch/` YAML is canonical.
- The canvas is view state only.
- Every visible object must map to a stable IR identity:
  - `unit:<id>`
  - `contract:<id>`
  - `data_model:<id>`
  - `flow:<id>`
- Layout and camera state are not architecture. Store them separately under `.arch/ui/`.

## Current backend contract

The backend already enforces these semantics.

### Units

Units live in `.arch/units/*.yaml`.

Relevant fields:

- `provides: [contract_id...]`
- `consumes: [contract_id...]`
- `requires: [unit_id...]`
- `generation_mode: managed|observed|opaque`
- `kind`
- `layer`
- `files`

Meaning:

- `provides` is a canonical `unit -> contract` edge.
- `consumes` is a canonical `unit -> contract` edge.
- `requires` is a canonical `unit -> unit` fallback edge for non-contract or opaque dependencies.

Validation rules:

- each consumed contract must exist
- each consumed contract must resolve to exactly one provider unit
- consumed contracts are layer-checked against their provider unit
- required units are layer-checked directly

Planning rule:

- `required_units = requires ∪ provider(consumes)`

The frontend should treat that as a derived execution detail, not as a separate user-owned architecture edge.

### Contracts and data models

These are separate collections:

- `.arch/contracts/*.yaml`
- `.arch/data_models/*.yaml`

The frontend should edit them directly, not as nested blobs inside units.

### Flows

Flows live in `.arch/flows/*.yaml`.

Current real behavior:

- `steps[].call` is real and validated against provided contract methods
- `steps[].emit` is real in a narrow sense:
  - event name must exist
  - the emitting trigger unit must depend on the registry that owns that event
- `steps[].subscribe` is still metadata only

## Frontend rules

### Dependency editing

The UI should be contract-first, but honest.

Show three different things:

- `provides` as `unit -> contract`
- `consumes` as `unit -> contract`
- `requires` as `unit -> unit`

Do not collapse `requires` into `consumes`.
Do not invent `consumes` from `requires`.
Do not hide `requires` just because a unit also has `consumes`.

Good frontend behavior:

- if the user wants a typed interface dependency, edit `consumes`
- if the user wants an opaque or concrete unit dependency, edit `requires`
- if the backend derives a provider unit from `consumes`, show that as derived execution context, not canonical design state

### Pattern display

Use [docs/pattern-support-matrix.md](/Users/talian/priv/blueprint/docs/pattern-support-matrix.md) as the source of truth for pattern badges and UI affordances.

Rules:

- `real` means the frontend may expose first-class editing affordances
- `metadata` means the frontend may show the label, but should not imply deeper semantics
- unsupported patterns should not be creatable through the UI

Current important reality:

- `unit.registry` is real only in the narrow event-declaration sense
- `flow.emit` is real only in the narrow registry-event sense
- `flow.subscribe`, `unit.hook`, and `unit.event_handler` are not first-class yet

### Valid edits only

The frontend must not allow "draw now, interpret later".

It should only write edits that are already schema-legal or that can be completed in one transaction into a schema-legal state.

Examples:

- creating a new consumed contract edge should either:
  - connect to an existing contract, or
  - create the contract document in the same operation
- creating a new contract should also let the user assign exactly one provider unit, or leave the model invalid on purpose and show that state clearly

## Readiness model

These states are derived, not canonical:

- `draft`: missing required fields or schema-invalid
- `defined`: schema-valid but cross-file validation fails
- `compilable`: `blueprint validate-ir` passes
- `planned`: `blueprint plan-jobs` succeeds
- `verified`: `blueprint verify` passes

Use these states to gate UI actions.

Examples:

- do not offer coder execution when the repo is not at least `planned`
- show invalid `consumes` edges as validation failures, not as vague warnings

## Backend entrypoints the frontend can rely on

The frontend does not need a new backend surface yet.
It can use the existing CLI and artifacts.

Stable lane:

- `blueprint validate-ir`
- `blueprint create-revision`
- `blueprint compile`
- `blueprint plan-jobs`
- `blueprint write-job-manifests`
- `blueprint prepare-job-worktree`
- `blueprint run-coder-job`
- `blueprint write-execution-result`
- `blueprint verify-execution-result`
- `blueprint show-execution-diff`
- `blueprint remove-job-worktree`

That is enough for:

- architecture editing
- validation
- planning
- bounded execution
- diff review

## Host strategy

Build one web UI and embed it in hosts.

- JetBrains first
- VS Code later

The UI core should stay host-agnostic.
Host adapters should do only:

- read/write files under `.arch/`
- run backend commands
- reveal/open files
- stream progress and diagnostics

## Non-goals for the frontend

Do not add frontend-only architecture concepts.

Do not add:

- fake contract consumption that is not backed by `consumes`
- generalized event systems beyond current registry-event support
- hook semantics
- inheritance editors
- decorator semantics

If the backend does not model it, the frontend should not pretend it does.
