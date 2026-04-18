**Pattern Support**

This file is the current backend truth for pattern support.

Rules:
- `real` means the backend has concrete behavior for the pattern today.
- `metadata` means the backend accepts the name, but does not interpret it beyond carrying it through the IR.
- Anything not listed here is unsupported and should not appear in `.arch/units/*.yaml` or conformance case tags.

**Case Tags**
These are the pattern labels used in conformance cases to describe what a fixture is testing.

| Pattern | Status | Meaning |
| --- | --- | --- |
| `unit.service` | `real` | Unit kind with planning, ownership, and dependency semantics. |
| `unit.adapter` | `real` | Unit kind with planning, ownership, and dependency semantics. |
| `unit.registry` | `metadata` | Known unit boundary only. No registry-specific compiler or verifier behavior. |
| `unit.hook` | `metadata` | Known unit boundary only. No hook-specific compiler or verifier behavior. |
| `unit.event_handler` | `metadata` | Known unit boundary only. No event-handler-specific compiler or verifier behavior. |
| `unit.task` | `metadata` | Known unit boundary only. No task-specific compiler or verifier behavior. |
| `contract.protocol` | `real` | Compiled and verified as a Python `Protocol` contract. |
| `contract.abc` | `real` | Compiled and verified as a Python `ABC` contract. |
| `model.dataclass` | `real` | Compiled and verified as a Python dataclass model. |
| `model.typed_dict` | `real` | Compiled as a Python `TypedDict` model. |
| `flow.call` | `real` | Validated against unit and provided contract method names. |
| `flow.emit` | `metadata` | Flow syntax only. Event emission semantics are not enforced yet. |
| `flow.subscribe` | `metadata` | Flow syntax only. Subscription semantics are not enforced yet. |
| `policy.layer_rules` | `real` | Layer dependency rules are enforced during IR validation. |
| `ownership.compiler_files` | `real` | Compiler-owned file boundaries are enforced during IR validation. |
| `repo.missing_required_file` | `real` | Required `.arch` files and directories are enforced during IR validation. |

**Unit Pattern Names**
These are the currently accepted values for `units/*.yaml -> patterns`.

| Pattern | Status | Meaning |
| --- | --- | --- |
| `constructor_injection` | `metadata` | Known unit pattern name only. No constructor-injection analysis yet. |
| `protocol_contract` | `metadata` | Known unit pattern name only. Real contract behavior comes from `contracts/*.yaml`. |
| `abc_contract` | `metadata` | Known unit pattern name only. Real contract behavior comes from `contracts/*.yaml`. |
| `dataclass_model` | `metadata` | Known unit pattern name only. Real model behavior comes from `data_models/*.yaml`. |
| `typed_dict_model` | `metadata` | Known unit pattern name only. Real model behavior comes from `data_models/*.yaml`. |
| `registry` | `metadata` | Known unit pattern name only. No registry adapter exists yet. |
| `hook` | `metadata` | Known unit pattern name only. No hook adapter exists yet. |
| `event_handler` | `metadata` | Known unit pattern name only. No event handler adapter exists yet. |
| `cli_command` | `metadata` | Known unit pattern name only. No CLI command adapter exists yet. |

**Not Supported**

These are not modeled as first-class backend patterns today:
- semantic decorators
- policy decorators
- deep inheritance
- multiple inheritance
- metaclasses
- monkey patching
- runtime-generated classes or functions
- framework magic with hidden runtime semantics

**Interpretation Notes**

- Composition is supported implicitly through unit boundaries, contracts, flows, and ownership. It is not a standalone pattern identifier.
- General inheritance is not supported. The only narrow supported inheritance case is contract emission as `ABC`.
- Registries and hooks are known names in the IR, but still metadata. The backend does not yet parse, emit, or verify their runtime semantics.
