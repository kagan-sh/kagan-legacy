"""Lint test files for tautological patterns and test-smell anti-patterns.

Scans Python test files under tests/ for:
  - Test functions where the ONLY assertion is `assert X is not None`
  - `assert True` or `assert 1` literals
  - Private-attribute reach-in assertions (rule 6)
  - Over-mocking the SUT's own private methods — depth >= 3 (rule 5)

Round-trip tautology (rule 1) and name-claim mismatch (rule 2) are NOT
AST-detectable; they remain review-only — do not assume this linter covers them.

Tests that use ``pytest.raises`` / ``pytest.warns`` as context managers or
that have no asserts at all (valid "does not crash" tests) are not flagged.
"""

import ast
import re
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent.parent / "tests"
SKIP_DIRS = {"helpers", "__pycache__", ".pytest_cache"}
_NOQA_RE = re.compile(
    r"check-test-quality:\s*noqa\s+(rule-[56]|private-assert|over-mock)",
    re.IGNORECASE,
)


def _iter_test_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("test_*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _line_has_noqa(source: str, lineno: int, *, rule: str) -> bool:
    lines = source.splitlines()
    if lineno < 1 or lineno > len(lines):
        return False
    line = lines[lineno - 1]
    if f"noqa {rule}" in line.lower():
        return True
    if rule == "rule-6" and "noqa private-assert" in line.lower():
        return True
    if rule == "rule-5" and "noqa over-mock" in line.lower():
        return True
    return _NOQA_RE.search(line) is not None


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
            if isinstance(func, ast.Attribute) and func.attr in ("raises", "warns"):
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    return True
    return False


def _is_private_name(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


_SUT_PRIVATE_BASES = frozenset({"core", "session", "git", "reset_mod"})


def _assert_reaches_private(node: ast.AST) -> bool:
    """True when an assert reads core/session private state or calls their privates."""
    for child in ast.walk(node.test):
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            base = child.value.id
            if base in ("core", "session") and _is_private_name(child.attr):
                return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                base = func.value.id
                if base in _SUT_PRIVATE_BASES and _is_private_name(func.attr):
                    return True
    return False


def _count_private_mock_stubs(func_node: ast.AST) -> int:
    """Count monkeypatch.setattr / setattr calls stubbing a private method name."""
    count = 0
    for child in ast.walk(func_node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "setattr":
                if len(child.args) >= 2:
                    attr = child.args[1]
                    if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                        if _is_private_name(attr.value):
                            count += 1
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "setattr"
                and isinstance(func.value, ast.Name)
                and func.value.id == "monkeypatch"
            ):
                if len(child.args) >= 2:
                    attr = child.args[1]
                    if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                        if _is_private_name(attr.value):
                            count += 1
    return count


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

        if not asserts and not has_pytest_cm:
            continue

        for a in asserts:
            if _is_assert_literal_true(a):
                findings.append(
                    _Finding(path, a.lineno, node.name, "assert True / assert 1")
                )
            if _assert_reaches_private(a) and not _line_has_noqa(source, a.lineno, rule="rule-6"):
                findings.append(
                    _Finding(
                        path,
                        a.lineno,
                        node.name,
                        "private-attr reach-in assertion (rule 6)",
                    )
                )

        if asserts and not has_pytest_cm and all(_is_assert_not_none(a) for a in asserts):
            findings.append(
                _Finding(
                    path,
                    asserts[0].lineno,
                    node.name,
                    "only assertion is `assert X is not None`",
                )
            )

        private_stubs = _count_private_mock_stubs(node)
        if private_stubs >= 3 and not _line_has_noqa(source, node.lineno, rule="rule-5"):
            findings.append(
                _Finding(
                    path,
                    node.lineno,
                    node.name,
                    f"over-mock depth {private_stubs} private stubs (rule 5)",
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
