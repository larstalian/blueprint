# Backend Spec

## Goal

Build a backend that lets a senior engineer own the architecture and constraints while agents do bounded implementation work.

The backend is:

- a versioned architecture IR in the repo
- a deterministic compiler over that IR
- a reconciler that compares code to IR
- a planner, executor, and verifier for bounded unit jobs

It is not:

- a diagram store
- a repo-wide agent runner
- a promise to round-trip arbitrary Python

## Hard rules

1. The canonical source of truth lives in the repo.
2. The backend is a modular monolith in v1.
3. Ownership is file-level in v1.
4. Compiler output is deterministic for a fixed IR revision and compiler version.
5. Agent output is only allowed inside owned files.
6. Reverse compile is recovery with confidence, not assumed truth.
7. A patch is accepted only if the verifier passes.

## Repo layout

Use `.arch/` as the canonical model root.

```text
repo/
  .arch/
    system.yaml
    units/
      payment_service.yaml
      payment_gateway.yaml
    contracts/
      payment_authorizer.yaml
    data_models/
      payment_request.yaml
      payment_result.yaml
    flows/
      checkout_flow.yaml
    ownership.yaml
    policies.yaml
    manifests/
      compiler.lock.json
    reports/
      recovery.yaml
      drift.json
    cache.sqlite
```

Rules:

- committed canonical files:
  - `system.yaml`
  - `units/*.yaml`
  - `contracts/*.yaml`
  - `data_models/*.yaml`
  - `flows/*.yaml`
  - `ownership.yaml`
  - `policies.yaml`
- committed generated files:
  - `manifests/compiler.lock.json`
- derived, not canonical:
  - `reports/recovery.yaml`
  - `reports/drift.json`
  - `cache.sqlite`

`cache.sqlite` must be ignored. It is a local index, not model state.

## Canonical IR files

### `system.yaml`

Purpose:

- top-level system metadata
- language and runtime settings
- compiler settings
- conventions that apply across units

Minimum shape:

```yaml
schema_version: 1
system_id: checkout
language: python
python:
  version: "3.13"
  package_root: app
compiler:
  generated_root: app
  tests_root: tests
conventions:
  test_framework: pytest
  type_checker: pyright
  formatter: ruff
```

### `units/*.yaml`

Purpose:

- architecture-bearing implementation units
- unit ownership
- dependency contracts
- allowed patterns

Minimum shape:

```yaml
id: payment_service
kind: service
language: python
generation_mode: managed
files:
  - app/payments/service.py
provides:
  - payment_authorizer
requires:
  - payment_gateway
  - audit_logger
  - event_bus
patterns:
  - constructor_injection
  - protocol_contract
tests:
  - tests/unit/payments/test_service.py
  - tests/contracts/test_payment_authorizer.py
policies:
  side_effects:
    network: true
    filesystem: false
  concurrency: sync
```

Required fields:

- `id`
- `kind`
- `language`
- `generation_mode`
- `files`

Optional fields:

- `provides`
- `requires`
- `patterns`
- `tests`
- `policies`

Rules:

- `files` is the canonical ownership boundary in v1.
- A file can be owned by one managed unit only.
- `generation_mode` must be one of:
  - `managed`
  - `observed`
  - `opaque`

Meaning:

- `managed`: compiler and planner may create jobs against this unit
- `observed`: importer tracks it, but no agent job is emitted
- `opaque`: known boundary, unsupported internally

### `contracts/*.yaml`

Purpose:

- stable service or port contracts
- compile target for protocols or ABCs
- verifier target for contract tests

Minimum shape:

```yaml
id: payment_authorizer
kind: protocol
module: app/payments/contracts.py
symbol: PaymentAuthorizer
methods:
  - name: authorize
    params:
      - name: request
        type: PaymentRequest
    returns: PaymentResult
```

Required fields:

- `id`
- `kind`
- `module`
- `symbol`

### `data_models/*.yaml`

Purpose:

- stable payload and domain data shapes

Minimum shape:

```yaml
id: payment_request
kind: dataclass
module: app/payments/models.py
symbol: PaymentRequest
fields:
  - name: amount
    type: Decimal
  - name: currency
    type: str
```

Required fields:

- `id`
- `kind`
- `module`
- `symbol`
- `fields`

### `flows/*.yaml`

Purpose:

- sequence-level behavior that matters to architecture
- event or call relationships the verifier should enforce

Minimum shape:

```yaml
id: checkout_flow
trigger:
  type: call
  unit: checkout_service
  contract: start_checkout
steps:
  - call: payment_service.authorize
  - emit: payment_authorized
  - call: audit_logger.record
```

Required fields:

- `id`
- `trigger`
- `steps`

### `ownership.yaml`

Purpose:

- global ownership map
- compiler-owned generated files
- conflict detection

Minimum shape:

```yaml
unit_files:
  payment_service:
    - app/payments/service.py
  payment_gateway:
    - app/payments/gateway.py
compiler_files:
  - app/payments/contracts.py
  - app/payments/models.py
  - tests/contracts/test_payment_authorizer.py
```

Rules:

- `unit_files` must match the union of `files` in managed units.
- `compiler_files` are never direct agent targets.
- no file may appear in both `unit_files` and `compiler_files`.

### `policies.yaml`

Purpose:

- system-wide policy rules
- dependency rules
- import restrictions
- runtime behavior constraints

Minimum shape:

```yaml
layers:
  - api
  - service
  - domain
  - infra
allowed_dependencies:
  api: [service, domain]
  service: [domain, infra]
  domain: []
  infra: [domain]
forbidden_imports:
  - flask
side_effect_defaults:
  network: false
  filesystem: false
```

### `reports/recovery.yaml`

Purpose:

- importer output
- recovery evidence
- unsupported zones

This file is derived. It is not canonical until the user accepts changes into the IR.

Minimum shape:

```yaml
recovered_units:
  - id: payment_service
    confidence: high
    inferred_from:
      - app/payments/service.py
    ambiguities: []
unsupported_zones:
  - file: app/legacy/runtime_magic.py
    reason: runtime monkey patching
```

## Backend modules

Keep the backend as a modular monolith.

Suggested package layout:

```text
blueprint/
  ir/
  revisions/
  parser/
    python/
  compiler/
    python/
  planner/
  executor/
  verifier/
  reconciler/
  storage/
  cli/
```

Module responsibilities:

- `ir`: load, validate, normalize `.arch/*`
- `revisions`: immutable revision creation and diffing
- `parser/python`: Python indexing and pattern extraction
- `compiler/python`: deterministic emission of code and manifests
- `planner`: affected-unit analysis and job DAG creation
- `executor`: isolated agent job execution
- `verifier`: patch acceptance checks
- `reconciler`: code-to-IR and IR-to-code drift analysis
- `storage`: derived local state and run records
- `cli`: user-facing commands

## Revision model

The backend must reason over immutable IR revisions.

Revision inputs:

- normalized canonical IR files

Revision ID:

- `sha256` of the canonical serialized IR snapshot

Compiler version:

- stored separately
- never mixed into the revision ID

Why:

- the IR revision identifies the intended architecture
- the compiler version identifies how that architecture was emitted

Minimum compile record:

```json
{
  "revision_id": "9e0d5b...",
  "compiler_version": "0.1.0",
  "repo_commit": "abc123",
  "generated_at": "2026-04-18T20:30:00Z"
}
```

Store this in `.arch/manifests/compiler.lock.json`.

## Affected-unit calculation

A unit is affected if any of these change:

- its own unit file
- a contract it provides
- a contract it requires
- a data model it imports or references
- a flow step that names the unit
- a global policy that applies to the unit

Affected-unit calculation must be deterministic.

## Planner job model

The planner turns an IR diff into a DAG of unit jobs.

Job kinds in v1:

- `implement_unit`
- `refactor_unit`
- `reconcile_unit`

Minimum job shape:

```json
{
  "job_id": "job_payment_service_0001",
  "kind": "implement_unit",
  "unit_id": "payment_service",
  "target_revision_id": "9e0d5b...",
  "base_repo_commit": "abc123",
  "owned_files": [
    "app/payments/service.py"
  ],
  "readonly_files": [
    "app/payments/contracts.py",
    "app/payments/models.py"
  ],
  "acceptance_checks": [
    "ruff",
    "pyright",
    "pytest tests/unit/payments/test_service.py",
    "pytest tests/contracts/test_payment_authorizer.py"
  ]
}
```

Rules:

- a job must have at least one owned file
- a job may not own compiler files
- two runnable jobs may not own the same file
- dependent jobs wait until required contracts are generated and verified

## Job state machine

States:

- `planned`
- `ready`
- `running`
- `verifying`
- `passed`
- `failed`
- `stale`
- `merged`
- `rejected`

Transitions:

- `planned -> ready`
- `ready -> running`
- `running -> verifying`
- `verifying -> passed`
- `verifying -> failed`
- `passed -> merged`
- any non-final state -> `stale`
- `passed -> rejected`

Stale conditions:

- target repo commit changed and touched an owned file
- target repo commit changed and touched a required contract or generated file
- target IR revision changed
- planner recalculated ownership differently

Stale jobs must not merge. They must be replanned.

## Compiler

The compiler is deterministic.

It owns:

- package layout
- generated contract files
- generated model files
- generated test scaffolds
- architecture policy tests
- ownership manifest
- compiler lock manifest

It does not own:

- nontrivial method bodies
- repo-wide refactors
- files outside declared generated outputs

### Compile pipeline

1. Load and validate canonical IR.
2. Normalize IR and create immutable revision.
3. Compute affected units.
4. Generate compiler-owned files.
5. Create or refresh missing unit skeletons for managed units.
6. Update `ownership.yaml`.
7. Update `compiler.lock.json`.
8. Emit planner jobs for affected managed units.

Compiler output must be identical for the same:

- normalized IR revision
- compiler version

## Python parser

The Python parser has two jobs:

- read and index code
- support safe rewrites

Use:

- Tree-sitter for fast parse, indexing, and structural queries
- LibCST for precise rewrites that preserve formatting and comments

Do not try to make one library do both jobs.

### Parser outputs

- symbol table
- import graph
- module index
- decorator index
- call references
- class and function signatures

These outputs are derived and can live in `cache.sqlite`.

## Pattern adapters

Do not build one giant Python parser with hardcoded semantics.

Use a registry of pattern adapters.

Minimal interface:

```python
class PatternAdapter(Protocol):
    name: str

    def match(self, index: SymbolIndex) -> list[Match]: ...
    def extract(self, match: Match) -> IRFragment: ...
    def emit(self, fragment: IRFragment) -> EmissionPlan: ...
    def rewrite(self, path: str, target: IRFragment) -> Patch: ...
```

Builtin adapters for v1:

- `protocol_contract`
- `abc_contract`
- `dataclass_model`
- `service_with_constructor_injection`
- `registry`
- `hook`
- `event_handler`
- `cli_command`

Anything else is:

- unsupported
- opaque
- a plugin later

## Executor

The executor runs one job at a time per owned file set.

Execution rules:

- each job runs in an isolated worktree or sandbox
- owned files are writable
- everything else is readonly
- the agent receives only job context, not the whole repo by default
- any attempted write outside owned files fails the job

Minimum context bundle:

- target unit YAML
- required contract YAML files
- required data model YAML files
- readonly source files named in the job
- applicable policy rules
- acceptance checks

## Reproducibility record

Every agent run must record:

- `revision_id`
- `repo_commit`
- `job_id`
- `prompt_bundle_hash`
- `model_id`
- `tool_versions`
- `patch_digest`
- verifier results

This is not exact LLM determinism.
It is bounded, auditable generation.

## Verifier

The verifier decides acceptance.

Verifier order:

1. ownership check
2. parse check
3. formatter and lint
4. type check
5. unit tests
6. contract tests
7. architecture dependency tests
8. drift check against target IR revision

If any step fails, the patch is rejected.

## Reconciler

The reconciler compares the repo and the IR.

It has two jobs:

- recover architecture candidates from code
- detect drift between code and managed IR

### Recovery pipeline

1. Parse Python files and build an index.
2. Run pattern adapters.
3. Build recovered units, contracts, models, and flows.
4. Score confidence.
5. Emit `reports/recovery.yaml`.
6. Wait for user acceptance before touching canonical IR.

### Drift categories

- `model_to_code`
- `code_to_model`
- `policy_to_implementation`

### Drift report fields

- entity ID
- file path
- drift category
- supported or unsupported
- recoverable or not
- confidence

## API surface

Start with CLI commands. Keep the backend service boundary clean enough to expose later.

Required commands:

- `validate-ir`
- `create-revision`
- `compile`
- `import-repo`
- `reconcile`
- `plan-jobs`
- `run-job`
- `verify-job`
- `merge-job`

These should map cleanly to Python functions:

```python
validate_ir(repo_path) -> Diagnostics
create_revision(repo_path) -> Revision
compile_ir(repo_path) -> CompileResult
import_repo(repo_path) -> RecoveryReport
reconcile(repo_path) -> DriftReport
plan_jobs(repo_path) -> JobDag
run_job(repo_path, job_id) -> PatchResult
verify_job(repo_path, job_id) -> VerificationResult
merge_job(repo_path, job_id) -> MergeResult
```

## Supported Python subset

Supported in v1:

- packages and modules
- classes and functions
- dataclasses
- protocols and ABCs
- constructor injection
- registries
- hooks
- sync and async functions
- event handlers
- pytest-based contract tests

Not supported in v1:

- metaclasses
- monkey patching
- runtime-generated classes or functions
- decorator systems with hidden runtime semantics
- multiple-inheritance-heavy code
- framework magic that hides behavior outside normal Python structure

## First milestone

The first milestone is not "AI wrote an app."

It is this:

1. Import a small Python repo.
2. Recover units and contracts into `reports/recovery.yaml`.
3. Accept two recovered units into canonical IR.
4. Change one contract in `.arch/contracts/`.
5. Run compile.
6. Emit one unit job.
7. Run the job in isolation.
8. Verify and merge the patch.
9. Reconcile and report no remaining drift for affected units.

If that works, the backend is real.

## Non-goals for v1

- no multi-language support
- no line-level or symbol-level write ownership
- no repo-wide agent edits
- no remote database as source of truth
- no promise to recover arbitrary Python exactly
- no distributed service architecture

## Bottom line

This backend is a compiler and reconciler over a versioned IR in the repo.

The compiler owns structure.
The planner owns bounded jobs.
The executor owns isolated patch generation.
The verifier decides acceptance.
The reconciler reports what the system understands and what it does not.
