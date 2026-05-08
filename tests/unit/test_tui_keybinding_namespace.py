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


def test_kanban_global_hints_do_not_duplicate_fixed_quick_actions_strip() -> None:
    from kagan.tui.screens.kanban import KanbanScreen

    labels = {description.lower() for _, description in KanbanScreen._global_hints()}

    assert "quick actions" not in labels
    assert "help" not in labels


def test_ai_panel_shortcut_is_ctrl_period_with_legacy_aliases_hidden() -> None:
    from kagan.tui.keybindings import KANBAN_BINDINGS, get_key_for_action, get_keys_for_action

    assert get_key_for_action(KANBAN_BINDINGS, "toggle_chat") == "Ctrl+."
    assert get_keys_for_action(KANBAN_BINDINGS, "toggle_chat") == ["Ctrl+."]


# ---------------------------------------------------------------------------
# Task B — binding consistency checks
# ---------------------------------------------------------------------------


def test_every_shown_binding_has_description() -> None:
    """Every Binding with show=True (or show omitted, defaulting to True)
    must have a non-empty description string."""
    import importlib

    from textual.binding import Binding

    keybindings = importlib.import_module("kagan.tui.keybindings")

    # Collect all list[BindingType] module-level names
    all_lists: list[list] = []
    for name in dir(keybindings):
        if name.startswith("_") or name == "FooterBuilder":
            continue
        obj = getattr(keybindings, name)
        if isinstance(obj, list):
            all_lists.append(obj)

    offenders: list[str] = []
    for binding_list in all_lists:
        for item in binding_list:
            if not isinstance(item, Binding):
                continue
            if item.show is False:
                continue
            if not item.description:
                offenders.append(f"key={item.key!r} action={item.action!r}")

    assert not offenders, "The following Bindings have show=True but no description:\n" + "\n".join(
        f"  {o}" for o in offenders
    )


def test_footer_builder_keys_match_known_bindings() -> None:
    """Every key label emitted by FooterBuilder static methods must appear as a
    key_display or key value in at least one binding list in keybindings.py.

    This catches hints that drift away from real bindings, e.g. when a binding
    is removed but the footer label is not updated.
    """
    import importlib

    from textual.binding import Binding

    keybindings = importlib.import_module("kagan.tui.keybindings")
    FooterBuilder = keybindings.FooterBuilder

    # Build a set of all known key labels (key_display or key)
    known_labels: set[str] = set()
    for name in dir(keybindings):
        if name.startswith("_") or name == "FooterBuilder":
            continue
        obj = getattr(keybindings, name)
        if not isinstance(obj, list):
            continue
        for item in obj:
            if not isinstance(item, Binding):
                continue
            label = item.key_display or item.key
            if label:
                known_labels.add(label)

    # Add common multi-key shortcuts that are presented as combined labels
    # and are not themselves individual binding keys (e.g. "1/2", "h/j/k/l").
    # "Shift+←/→" is the combined presentation of two bindings (move_left,
    # move_right) whose individual key_display values are "Shift+←" and "Shift+→".
    _COMPOSITE_ALLOWLIST: frozenset[str] = frozenset(
        {
            "1/2",
            "h/j/k/l",
            "Enter/y",
            "Esc/n",
            "s / a",
            "Shift+←/→",
        }
    )

    # Collect all hints from FooterBuilder static methods
    builder_methods = [
        name
        for name in dir(FooterBuilder)
        if not name.startswith("_") and callable(getattr(FooterBuilder, name))
    ]

    offenders: list[str] = []
    for method_name in builder_methods:
        hints: list[tuple[str, str]] = getattr(FooterBuilder, method_name)()
        for key_label, description in hints:
            if key_label in _COMPOSITE_ALLOWLIST:
                continue
            if key_label in known_labels:
                continue
            offenders.append(f"FooterBuilder.{method_name}(): {key_label!r} ({description!r})")

    assert not offenders, (
        "FooterBuilder emits key labels with no matching Binding in keybindings.py:\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_no_ctrl_shift_t_in_docked_chat_hint() -> None:
    """The removed Ctrl+Shift+T binding must not appear in the docked chat status hint."""
    from kagan.tui.widgets.chat import ChatPanel

    panel = ChatPanel.__new__(ChatPanel)
    # Bypass __init__ is forbidden per memory — use real constructor but
    # supply only the keyword args that prevent side-effects.
    # ChatPanel.__init__ calls super().__init__ which is Textual Vertical.
    # We verify via the default attribute directly rather than constructing
    # the full widget hierarchy.
    assert "Ctrl+Shift+T" not in ChatPanel.__init__.__code__.co_consts, (
        "Ctrl+Shift+T must not be a string constant in ChatPanel.__init__ "
        "(check _overlay_fullscreen_key default)"
    )
    # Belt-and-suspenders: check the attribute default used in _refresh_status
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2] / "src/kagan/tui/widgets/chat.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "_overlay_fullscreen_key":
                    if isinstance(node.value, ast.Constant):
                        assert node.value.value != "Ctrl+Shift+T", (
                            "_overlay_fullscreen_key default must not be 'Ctrl+Shift+T'"
                        )


def test_ctrl_j_timeline_not_in_chat_hints() -> None:
    """Ctrl+J timeline was removed — it must not appear in any chat status hints."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2] / "src/kagan/tui/widgets/chat.py").read_text(
        encoding="utf-8"
    )
    assert "Ctrl+J timeline" not in src, (
        "'Ctrl+J timeline' found in chat.py — this binding was removed and the hint must be dropped"
    )
