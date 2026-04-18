"""Minimal deterministic emitter for compiler-owned files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from blueprint.revisions import Revision, RevisionValidationError, create_revision


TYPE_IMPORTS = {
    "Decimal": ("decimal", "Decimal"),
    "UUID": ("uuid", "UUID"),
    "date": ("datetime", "date"),
    "datetime": ("datetime", "datetime"),
}


@dataclass(frozen=True)
class CompileResult:
    revision_id: str
    emitted_files: tuple[str, ...]


class CompileError(ValueError):
    """Raised when deterministic emission cannot satisfy the declared IR."""


def compile_ir(repo_root: Path) -> CompileResult:
    repo_root = Path(repo_root).resolve()
    revision = create_revision(repo_root)
    rendered_files = build_compiler_outputs(revision)

    for relative_path, content in rendered_files.items():
        output_path = repo_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    return CompileResult(
        revision_id=revision.revision_id,
        emitted_files=tuple(sorted(rendered_files)),
    )


def build_compiler_outputs(revision: Revision) -> Dict[str, str]:
    snapshot = revision.snapshot
    compiler_files = set(snapshot["ownership"]["compiler_files"])
    system = snapshot["system"]
    tests_root = system["compiler"]["tests_root"].rstrip("/")

    contracts = snapshot["collections"]["contracts"]
    data_models = snapshot["collections"]["data_models"]

    outputs: Dict[str, str] = {}

    contract_groups = _group_by_path(contracts, "module")
    for module_path, grouped_contracts in contract_groups.items():
        if module_path not in compiler_files:
            continue
        outputs[module_path] = _render_contract_module(module_path, grouped_contracts, data_models)

    data_model_groups = _group_by_path(data_models, "module")
    for module_path, grouped_models in data_model_groups.items():
        if module_path not in compiler_files:
            continue
        outputs[module_path] = _render_data_model_module(module_path, grouped_models, data_models)

    for contract in contracts:
        test_path = f"{tests_root}/contracts/test_{contract['id']}.py"
        if test_path in compiler_files:
            outputs[test_path] = _render_contract_test_scaffold(contract)

    missing_outputs = sorted(compiler_files.difference(outputs))
    if missing_outputs:
        raise CompileError(
            "no deterministic emitter for compiler-owned file(s): "
            + ", ".join(missing_outputs)
        )

    return dict(sorted(outputs.items()))


def _group_by_path(documents: Iterable[Mapping[str, Any]], key: str) -> Dict[str, list[Mapping[str, Any]]]:
    grouped: Dict[str, list[Mapping[str, Any]]] = {}
    for document in documents:
        path = document.get(key)
        if isinstance(path, str) and path:
            grouped.setdefault(path, []).append(document)
    return {
        path: sorted(grouped_documents, key=lambda item: item["identity"]["entity_id"])
        for path, grouped_documents in sorted(grouped.items())
    }


def _render_contract_module(
    module_path: str,
    contracts: list[Mapping[str, Any]],
    data_models: list[Mapping[str, Any]],
) -> str:
    lines = [
        '"""Generated contract definitions."""',
        "",
        "from __future__ import annotations",
        "",
    ]

    contract_kinds = {contract["kind"] for contract in contracts}
    if "abc" in contract_kinds:
        lines.append("from abc import ABC, abstractmethod")
    if "protocol" in contract_kinds:
        lines.append("from typing import Protocol")

    model_symbol_to_module = {
        model["symbol"]: model["module"]
        for model in data_models
        if isinstance(model.get("symbol"), str) and isinstance(model.get("module"), str)
    }
    builtin_import_lines, local_import_lines = _render_type_imports(
        current_module_path=module_path,
        expressions=_iter_contract_type_expressions(contracts),
        symbol_to_module=model_symbol_to_module,
    )
    if builtin_import_lines:
        lines.extend(builtin_import_lines)
    if local_import_lines:
        if lines[-1] != "":
            lines.append("")
        lines.extend(local_import_lines)

    if lines[-1] != "":
        lines.append("")

    for index, contract in enumerate(contracts):
        if index:
            lines.extend(["", ""])
        lines.extend(_render_contract_definition(contract))

    return "\n".join(lines) + "\n"


def _render_contract_definition(contract: Mapping[str, Any]) -> list[str]:
    symbol = contract["symbol"]
    if contract["kind"] == "protocol":
        lines = [f"class {symbol}(Protocol):"]
        indent = "    "
        decorator = None
    else:
        lines = [f"class {symbol}(ABC):"]
        indent = "    "
        decorator = "@abstractmethod"

    methods = contract.get("methods", [])
    if not methods:
        lines.append(f"{indent}pass")
        return lines

    for method in methods:
        if decorator:
            lines.append(f"{indent}{decorator}")
        lines.append(f"{indent}{_render_method_signature(method)}")

    return lines


def _render_method_signature(method: Mapping[str, Any]) -> str:
    params = []
    for param in method.get("params", []):
        params.append(f"{param['name']}: {param['type']}")
    joined_params = ", ".join(["self", *params])
    return_annotation = method["returns"]
    return f"def {method['name']}({joined_params}) -> {return_annotation}: ..."


def _render_data_model_module(
    module_path: str,
    models: list[Mapping[str, Any]],
    all_models: list[Mapping[str, Any]],
) -> str:
    lines = [
        '"""Generated data model definitions."""',
        "",
        "from __future__ import annotations",
        "",
    ]

    model_kinds = {model["kind"] for model in models}
    if "dataclass" in model_kinds:
        lines.append("from dataclasses import dataclass")
    if "typed_dict" in model_kinds:
        lines.append("from typing import TypedDict")

    model_symbol_to_module = {
        model["symbol"]: model["module"]
        for model in all_models
        if isinstance(model.get("symbol"), str) and isinstance(model.get("module"), str)
    }
    builtin_import_lines, local_import_lines = _render_type_imports(
        current_module_path=module_path,
        expressions=_iter_data_model_type_expressions(models),
        symbol_to_module=model_symbol_to_module,
    )
    if builtin_import_lines:
        lines.extend(builtin_import_lines)
    if local_import_lines:
        if lines[-1] != "":
            lines.append("")
        lines.extend(local_import_lines)

    if lines[-1] != "":
        lines.append("")

    for index, model in enumerate(models):
        if index:
            lines.extend(["", ""])
        lines.extend(_render_data_model_definition(model))

    return "\n".join(lines) + "\n"


def _render_data_model_definition(model: Mapping[str, Any]) -> list[str]:
    kind = model["kind"]
    symbol = model["symbol"]
    fields = model.get("fields", [])

    if kind == "dataclass":
        lines = ["@dataclass(slots=True)", f"class {symbol}:"]
        if not fields:
            lines.append("    pass")
            return lines
        for field in fields:
            lines.append(f"    {field['name']}: {field['type']}")
        return lines

    if kind == "typed_dict":
        lines = [f"class {symbol}(TypedDict):"]
        if not fields:
            lines.append("    pass")
            return lines
        for field in fields:
            lines.append(f"    {field['name']}: {field['type']}")
        return lines

    lines = [f"class {symbol}:"]
    if not fields:
        lines.append("    pass")
        return lines
    for field in fields:
        lines.append(f"    {field['name']}: {field['type']}")
    return lines


def _render_contract_test_scaffold(contract: Mapping[str, Any]) -> str:
    contract_id = contract["id"]
    symbol = contract["symbol"]
    module_import = _module_path_to_import_path(contract["module"])
    return "\n".join(
        [
            f'"""Generated contract scaffold for {symbol}."""',
            "",
            "from __future__ import annotations",
            "",
            "import pytest",
            "",
            f"from {module_import} import {symbol}",
            "",
            "",
            f"def test_{contract_id}_contract_scaffold() -> None:",
            f"    _ = {symbol}",
            f'    pytest.skip("Implement contract assertions for {symbol}")',
            "",
        ]
    )


def _render_type_imports(
    current_module_path: str,
    expressions: Iterable[str],
    symbol_to_module: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    builtin_imports: Dict[str, set[str]] = {}
    model_imports: Dict[str, set[str]] = {}

    for expression in expressions:
        short_name = expression.rsplit(".", 1)[-1]
        builtin_import = TYPE_IMPORTS.get(short_name)
        if builtin_import is not None:
            module_name, symbol_name = builtin_import
            builtin_imports.setdefault(module_name, set()).add(symbol_name)
            continue

        target_module = symbol_to_module.get(short_name)
        if target_module and target_module != current_module_path:
            model_imports.setdefault(target_module, set()).add(short_name)

    builtin_lines: list[str] = []
    for module_name, symbols in sorted(builtin_imports.items()):
        builtin_lines.append(f"from {module_name} import {', '.join(sorted(symbols))}")
    local_lines: list[str] = []
    for module_path, symbols in sorted(model_imports.items()):
        local_lines.append(
            f"from {_module_path_to_import_path(module_path)} import {', '.join(sorted(symbols))}"
        )
    return builtin_lines, local_lines


def _iter_contract_type_expressions(contracts: Iterable[Mapping[str, Any]]) -> Iterable[str]:
    for contract in contracts:
        for method in contract.get("methods", []):
            for param in method.get("params", []):
                yield param["type"]
            yield method["returns"]


def _iter_data_model_type_expressions(models: Iterable[Mapping[str, Any]]) -> Iterable[str]:
    for model in models:
        for field in model.get("fields", []):
            yield field["type"]


def _module_path_to_import_path(module_path: str) -> str:
    if not module_path.endswith(".py"):
        raise CompileError(f"expected Python module path, got '{module_path}'")
    return module_path[:-3].replace("/", ".")
