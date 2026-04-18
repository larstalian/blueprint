from pathlib import Path
import shutil

from blueprint.compiler import compile_ir


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def test_compile_ir_emits_expected_compiler_owned_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    result = compile_ir(repo_root)

    assert result.emitted_files == (
        "app/payments/contracts.py",
        "app/payments/models.py",
        "tests/contracts/test_payment_authorizer.py",
    )
    assert read_file(repo_root / "app/payments/contracts.py") == read_file(
        FIXTURES_ROOT / "minimal_valid_repo_expected_output/app/payments/contracts.py"
    )
    assert read_file(repo_root / "app/payments/models.py") == read_file(
        FIXTURES_ROOT / "minimal_valid_repo_expected_output/app/payments/models.py"
    )
    assert read_file(repo_root / "tests/contracts/test_payment_authorizer.py") == read_file(
        FIXTURES_ROOT
        / "minimal_valid_repo_expected_output/tests/contracts/test_payment_authorizer.py"
    )


def test_compile_ir_is_idempotent(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(FIXTURES_ROOT / "minimal_valid_repo", repo_root)

    first = compile_ir(repo_root)
    second = compile_ir(repo_root)

    assert first.revision_id == second.revision_id
    assert first.emitted_files == second.emitted_files
    assert read_file(repo_root / "app/payments/contracts.py") == read_file(
        FIXTURES_ROOT / "minimal_valid_repo_expected_output/app/payments/contracts.py"
    )


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")

