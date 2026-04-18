# Backend V1

## What this backend is

This is not an "AI generates repo" backend.

It is a **control plane for architecture-first development**:

- the repo owns the architecture model
- the compiler owns structure and wiring
- agents own bounded implementation work
- verification decides what gets accepted

If that line gets blurred, the product turns into vibe coding with nicer diagrams.

## Core rule

**The architecture IR is the source of truth.**

Not the diagram.
Not the generated code.
Not the database.

The backend should treat the system as a typed graph with stable identities, strict contracts, and explicit ownership.

## V1 scope

V1 should support one disciplined Python subset:

- packages and modules
- functions and classes
- dataclass-style models
- protocols and abstract contracts
- services and adapters
- events and handlers
- registries and hooks
- CLI tasks and jobs
- tests and architecture rules

V1 should not support:

- metaclasses
- runtime code generation
- monkey patching
- dynamic import tricks
- deep inheritance-heavy designs
- framework-specific magic beyond simple adapters

If the backend pretends to understand arbitrary Python, it will lie.

## Product invariants

These need to hold at all times:

1. Every component, contract, and edge has a stable ID.
2. Every generated artifact is traceable to an IR revision and compiler version.
3. Every implementation task has an explicit file ownership boundary.
4. Agents cannot edit outside owned files.
5. Code generation is deterministic for the same IR revision and compiler version.
6. Import from code back into IR is recovery with confidence, not assumed truth.
7. Verification gates decide acceptance, not model confidence.

## Recommended runtime shape

Do not build this as a distributed microservice system in v1.

Build a **modular monolith** with a job runner:

- one backend process
- one local queue
- one local metadata store
- repo-native model files

That keeps the system debuggable and makes local-first use possible.

## Storage model

The model should live in the repo as text files.

That matters for trust, review, versioning, and mergeability.

Suggested layout:

```text
.blueprint/
  model/
    system.yaml
    components/
    contracts/
    flows/
    policies/
  manifests/
    compiler.lock.json
    symbol-map.json
  reports/
    drift.json
    recovery.json
```

Keep runtime state out of the model:

- local job state
- caches
- agent logs
- index tables

That state can live in SQLite under `.blueprint/state.db` or a user cache dir.

## Core backend subsystems

### 1. Model store

Responsibility:

- load the IR from repo files
- validate schema
- resolve references
- enforce stable IDs
- expose canonical normalized snapshots

Rules:

- IDs are opaque and permanent
- names and paths can change without changing identity
- serialization is canonical and sorted

### 2. Revision engine

Responsibility:

- compute immutable revisions of the normalized IR
- diff revisions
- answer "what changed"
- drive downstream compile and work planning

Important detail:

The backend should reason over immutable revisions, not mutable in-memory graphs.

That gives reproducible compile and work planning.

### 3. Python compiler

Responsibility:

- turn an IR revision into deterministic code structure
- generate contracts, skeletons, wiring, architecture tests, and manifests
- never invent topology

The compiler should generate:

- package layout
- protocol or ABC contract files
- dataclass or typed payload definitions
- dependency manifests
- architecture tests
- stub implementation files if missing

The compiler should not:

- fill nontrivial bodies
- rename user files behind their back
- rewrite files it does not own

### 4. Recovery importer

Responsibility:

- parse existing Python code
- recover symbols, imports, dependencies, and known patterns
- map recovered structure back into IR suggestions
- mark unsupported or low-confidence areas

Inputs:

- source files
- existing manifests
- optional architecture annotations

Outputs:

- recovered components
- recovered contracts
- recovered edges
- confidence scores
- unsupported zones
- drift reports

This is not "round-trip everything".
This is structured recovery with proof attached.

### 5. Work planner

Responsibility:

- turn an IR diff into a DAG of bounded work units
- assign owned files per work unit
- derive required context and required checks

Each work unit should contain:

- component ID
- target revision
- owned files
- allowed dependencies
- contract surface
- acceptance tests
- implementation objective

If a work unit does not have file ownership and acceptance checks, it is not ready for an agent.

### 6. Agent runner

Responsibility:

- execute work units in isolation
- provide only relevant context
- capture patch, logs, and structured outcomes

Rules:

- use worktrees or isolated copies
- mount only owned files as writable
- pass contract and dependency context, not the whole repo by default
- reject patches that cross ownership boundaries

The runner should treat the LLM as an untrusted implementation worker, not as the architecture authority.

### 7. Verifier

Responsibility:

- decide whether a proposed patch is acceptable

Checks should include:

- file ownership check
- formatter and lint
- type check
- unit tests
- contract tests
- architecture dependency tests
- manifest drift check

A patch should merge only if the verifier passes.

### 8. Merge coordinator

Responsibility:

- apply verified work back to the target repo
- reject stale work
- rebase or rerun if the base revision moved

Do not try to be clever here.
If the target revision changed in a conflicting way, invalidate the work unit and rerun planning.

## IR shape

The backend IR should model software semantics, not UML syntax.

Minimum v1 entities:

- `component`
- `contract`
- `data_model`
- `flow`
- `policy`
- `implementation_unit`
- `test_contract`

Minimum v1 edge types:

- `depends_on`
- `implements`
- `calls`
- `emits`
- `subscribes_to`
- `registers_to`
- `owns`

Minimum component kinds:

- `package`
- `service`
- `adapter`
- `port`
- `model`
- `event_handler`
- `task`
- `registry`
- `hook`

Minimum policy categories:

- sync vs async
- side effects allowed
- dependency direction
- statefulness
- retry or transaction behavior

## Deterministic vs agentic boundary

This is the most important backend split.

### Deterministic side

Owns:

- IR parsing and normalization
- revisioning
- project skeleton generation
- wiring generation
- manifests
- dependency rules
- architecture tests
- work planning
- validation

### Agentic side

Owns:

- implementation bodies
- local refactors inside owned files
- test-driven fill-in work
- changes needed to satisfy declared contracts

If agents are allowed to invent structure, the backend failed.

## Python recovery strategy

Use a real CST pipeline, not plain AST alone.

The importer should build:

1. symbol table
2. import graph
3. call and dependency graph
4. pattern classification results
5. confidence-scored IR suggestions

Recognize only explicit pattern families in v1:

- service objects
- adapters
- protocol contracts
- dataclasses
- registries
- hook dispatch
- event publishers and subscribers
- CLI entrypoints

Decorator handling should be classified into:

- semantic decorators
- policy decorators
- opaque decorators

Opaque decorators stay opaque. Do not fake understanding.

## Ownership model

File ownership should be coarse in v1.

Do not start with line-level or region-level ownership. It is fragile.

Each implementation unit should own whole files or tight file groups, for example:

- `payments/service.py`
- `payments/contracts.py`
- `tests/payments/test_service.py`

Generated files should be separated from implementation files where possible.

Good split:

- generated contracts and wiring are compiler-owned
- implementation and tests are human or agent-owned

That avoids protected-region hacks in v1.

## Drift model

Drift is unavoidable. Treat it as a first-class backend concern.

There are three drift types:

1. `model_to_code`
2. `code_to_model`
3. `policy_to_implementation`

The backend should detect drift after:

- manual code edits
- agent output
- compiler runs
- repo imports

Every drift report should say:

- what changed
- what entity is affected
- whether the change is supported
- whether the backend can recover it automatically
- confidence level

## Suggested module boundaries

If this backend is implemented in Python, keep the modules boring:

```text
blueprint/
  model/
  revisions/
  compiler/
    python/
  importer/
    python/
  planner/
  runner/
  verifier/
  merge/
  storage/
  reports/
```

Avoid framework noise early.
The hard part is the domain model and the guarantees.

## Backend API surface

Even if the first use is CLI-only, define the backend around explicit commands:

- `load_model`
- `validate_model`
- `create_revision`
- `diff_revisions`
- `compile_revision`
- `recover_repo`
- `plan_work`
- `run_work_unit`
- `verify_patch`
- `merge_work_unit`
- `scan_drift`

Those commands matter more than whether you expose them through HTTP later.

## Minimal compile pipeline

1. Load model files.
2. Validate schema and references.
3. Normalize and create immutable revision.
4. Compute affected components.
5. Generate deterministic files and manifests.
6. Generate or refresh architecture tests.
7. Emit work DAG for incomplete implementation units.

## Minimal recovery pipeline

1. Parse Python files.
2. Build symbol and import graph.
3. Recover known entities and edges.
4. Match against existing manifests if present.
5. Score confidence.
6. Emit recovery report and optional model patch.

## Minimal agent execution pipeline

1. Select ready work unit from DAG.
2. Prepare isolated workspace.
3. Materialize owned files and readonly context.
4. Run agent with contract and acceptance context.
5. Capture patch.
6. Verify patch.
7. Merge or reject.

## What to build first

Build in this order:

1. Canonical IR files and schema validation.
2. Immutable revision engine.
3. Deterministic Python compiler.
4. Architecture test generation.
5. Work planner with file ownership.
6. Verifier.
7. Recovery importer.
8. Agent runner.

If steps 1 through 6 are weak, the agent runner will just hide the weakness.

## Hard non-goals for v1

- no multi-language support
- no arbitrary Python round-trip promise
- no line-level ownership
- no repo-wide freeform agent edits
- no framework plugins as a first step
- no distributed backend

## Bottom line

The backend is really four things:

- a repo-native architecture model
- a deterministic compiler
- a bounded work planner and runner
- a strict verifier and drift detector

That is the backend that gives a senior engineer leverage without giving up control.
