import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
TUI_ROOT = REPO_ROOT / "src/kagan/tui"
KEYBINDINGS_FILE = TUI_ROOT / "keybindings.py"


def _binding_call_lines(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "Binding":
            lines.append(node.lineno)
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "Binding":
            lines.append(node.lineno)
    return sorted(lines)


def test_keybindings_module_contains_binding_declarations() -> None:
    lines = _binding_call_lines(KEYBINDINGS_FILE)
    assert lines, "Expected Binding declarations in src/kagan/tui/keybindings.py"


def test_tui_modules_declare_bindings_only_in_keybindings_module() -> None:
    offenders: list[tuple[Path, list[int]]] = []
    for path in sorted(TUI_ROOT.rglob("*.py")):
        if path == KEYBINDINGS_FILE:
            continue
        lines = _binding_call_lines(path)
        if lines:
            offenders.append((path.relative_to(REPO_ROOT), lines))

    details = "\n".join(
        f"- {path}:{','.join(str(line) for line in lines)}" for path, lines in offenders
    )
    assert not offenders, (
        "Binding declarations must be centralized in src/kagan/tui/keybindings.py."
        f"\nFound declarations in:\n{details}"
    )
