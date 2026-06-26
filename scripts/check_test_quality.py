"""Lint test files for tautological patterns.

Scans Python test files under tests/ for:
  - Test functions where the ONLY assertion is `assert X is not None`
  - `assert True` or `assert 1` literals

Tests that use ``pytest.raises`` / ``pytest.warns`` as context managers or
that have no asserts at all (valid "does not crash" tests) are not flagged.
"""

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent.parent / "tests"
SKIP_DIRS = {"helpers", "__pycache__", ".pytest_cache"}


def _iter_test_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("test_*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _is_assert_not_none(node: ast.Assert) -> bool:
    """Return True if the assert is `assert X is not None`."""
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    return (
        isinstance(test.ops[0], ast.IsNot)
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is None
    )


def _is_assert_literal_true(node: ast.Assert) -> bool:
    """Return True if the assert is `assert True` or `assert 1`."""
    test = node.test
    if not isinstance(test, ast.Constant):
        return False
    return test.value is True or test.value == 1


def _has_pytest_context_manager(func_node: ast.AST) -> bool:
    """Return True if the function uses pytest.raises or pytest.warns as a context manager."""
    for child in ast.walk(func_node):
        if not isinstance(child, ast.With) and not isinstance(child, ast.AsyncWith):
            continue
        for item in child.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            # Match pytest.raises(...) or pytest.warns(...)
            if isinstance(func, ast.Attribute) and func.attr in ("raises", "warns"):
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    return True
    return False


class _Finding:
    def __init__(self, path: Path, line: int, func: str, kind: str) -> None:
        self.path = path
        self.line = line
        self.func = func
        self.kind = kind

    def __str__(self) -> str:
        rel = self.path.relative_to(TESTS_ROOT.parent)
        return f"  {rel}:{self.line}:{self.func} -- {self.kind}"


def _check_file(path: Path) -> list[_Finding]:
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    findings: list[_Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue

        asserts: list[ast.Assert] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                asserts.append(child)

        has_pytest_cm = _has_pytest_context_manager(node)

        # No asserts AND no pytest.raises/warns -- skip silently.
        # These are valid "does not crash" smoke tests.
        if not asserts and not has_pytest_cm:
            continue

        # Check for assert-literal-true
        for a in asserts:
            if _is_assert_literal_true(a):
                findings.append(
                    _Finding(path, a.lineno, node.name, "assert True / assert 1")
                )

        # Only flag "only assert X is not None" when there's no pytest.raises/warns
        if asserts and not has_pytest_cm and all(_is_assert_not_none(a) for a in asserts):
            findings.append(
                _Finding(
                    path,
                    asserts[0].lineno,
                    node.name,
                    "only assertion is `assert X is not None`",
                )
            )

    return findings


def main() -> int:
    files = _iter_test_files(TESTS_ROOT)
    if not files:
        print(f"No test files found under {TESTS_ROOT}")
        return 0

    all_findings: list[_Finding] = []
    for path in files:
        all_findings.extend(_check_file(path))

    print(f"Test quality check: scanned {len(files)} test files")

    if not all_findings:
        print("No tautological patterns found.")
        return 0

    print(f"Found {len(all_findings)} tautological pattern(s):")
    for finding in all_findings:
        print(finding)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
