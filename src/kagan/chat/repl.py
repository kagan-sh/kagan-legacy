"""Console setup, REPL banner, wave animation, git helpers, and entry points."""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from kagan.chat._completion import fuzzy_match
from kagan.chat.commands import SLASH_COMMAND_REGISTRY
from kagan.runtime_env import build_sanitized_subprocess_environment


class _SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        partial = text[1:].casefold()

        seen: set[str] = set()
        # 1. Fuzzy-match against command names
        for spec in SLASH_COMMAND_REGISTRY.specs():
            if fuzzy_match(partial, spec.name) and spec.name not in seen:
                seen.add(spec.name)
                yield Completion(
                    spec.name,
                    start_position=-len(partial),
                    display_meta=spec.description,
                )

        # 2. Exact-match aliases from registry
        for alias, target in SLASH_COMMAND_REGISTRY.aliases.items():
            if alias == partial and target not in seen:
                spec_obj = SLASH_COMMAND_REGISTRY.get(target)
                if spec_obj is not None:
                    seen.add(target)
                    yield Completion(
                        target,
                        start_position=-len(partial),
                        display_meta=f"(alias) {spec_obj.spec.description}",
                    )


@dataclass(slots=True)
class ToolbarState:
    agent_backend: str = ""
    project_name: str = ""
    turn_count: int = 0
    session_label: str = "orchestrator"
    context_pct: float | None = None
    workspace_label: str = ""
    is_streaming: bool = False


_TOOLBAR_STATE = ToolbarState()

_REPL_COLORS: Final[dict[str, str]] = {
    "bg": "#0B0A09",
    "surface": "#151311",
    "panel": "#1E1B17",
    "text": "#FFFFFF",
    "text_muted": "#B5AC9F",
    "text_soft": "#C2B9AD",
    "accent": "#3fb58e",
    "accent_soft": "#1D3A31",
    "primary": "#d4a84b",
}

_ANSI_REPL_COLORS: Final[dict[str, str]] = {
    "accent": "ansigreen",
    "muted": "ansibrightblack",
    "primary": "ansiyellow",
}

_BOOT_TIP_COMMAND: Final[str] = "/flow"
_BOOT_TIP_TEXT: Final[str] = "Walk through Plan -> Execute -> Orchestrate."
_SHORTCUT_HINT_IDLE: Final[str] = "Ctrl-J newline · Ctrl-C clear · Ctrl-D exit"
_SHORTCUT_HINT_STREAMING: Final[str] = "Esc stop & edit last · type ahead to queue"


def _supports_truecolor_terminal() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    colorterm = os.environ.get("COLORTERM", "").casefold()
    term = os.environ.get("TERM", "").casefold()
    return "truecolor" in colorterm or "24bit" in colorterm or "direct" in term


def _build_prompt_style_rules() -> dict[str, str]:
    if _supports_truecolor_terminal():
        return {
            "prompt": f"fg:{_REPL_COLORS['accent']} bold",
            "bottom-toolbar": (
                f"noreverse bg:{_REPL_COLORS['panel']} fg:{_REPL_COLORS['text_soft']}"
            ),
            "bottom-toolbar.text": (
                f"noreverse bg:{_REPL_COLORS['panel']} fg:{_REPL_COLORS['text']}"
            ),
            "bottom-toolbar.rule": f"fg:{_REPL_COLORS['accent_soft']}",
            "bottom-toolbar.status": f"fg:{_REPL_COLORS['text_muted']}",
            "bottom-toolbar.hint": f"fg:{_REPL_COLORS['text_soft']}",
            "bottom-toolbar.key": f"fg:{_REPL_COLORS['accent']} bold",
            "completion-menu": f"bg:{_REPL_COLORS['surface']} fg:{_REPL_COLORS['text_muted']}",
            "completion-menu.completion.current": (
                f"bg:{_REPL_COLORS['accent_soft']} fg:{_REPL_COLORS['text']} bold"
            ),
            "selected-text": f"noreverse bg:{_REPL_COLORS['accent']} fg:{_REPL_COLORS['bg']}",
        }
    return {
        "prompt": "fg:ansigreen bold",
        "bottom-toolbar": "noreverse bg:default fg:default",
        "bottom-toolbar.text": "noreverse bg:default fg:default",
        "bottom-toolbar.rule": "fg:ansibrightblack",
        "bottom-toolbar.status": "fg:ansibrightblack",
        "bottom-toolbar.hint": "fg:default",
        "bottom-toolbar.key": "fg:ansigreen bold",
        "completion-menu": "bg:default fg:default",
        "completion-menu.completion.current": "noreverse bg:ansigreen fg:ansiblack bold",
        "selected-text": "noreverse bg:ansigreen fg:ansiblack",
    }


_PROMPT_STYLE_RULES: Final[dict[str, str]] = _build_prompt_style_rules()


@dataclass(frozen=True, slots=True)
class SearchPickerOption:
    value: str
    label: str
    meta: str = ""

    @property
    def search_text(self) -> str:
        return f"{self.value} {self.label} {self.meta}".casefold()


class _SearchPickerCompleter(Completer):
    def __init__(self, options: Sequence[SearchPickerOption]) -> None:
        self._options = list(options)

    def get_completions(self, document, complete_event):
        del complete_event
        query = document.text_before_cursor.strip().casefold()
        for option in self._options:
            if query and not fuzzy_match(query, option.search_text):
                continue
            yield Completion(
                option.value,
                start_position=-len(document.text_before_cursor),
                display=option.label,
                display_meta=option.meta,
            )


def supports_interactive_picker() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _resolve_search_picker_value(
    query: str,
    options: Sequence[SearchPickerOption],
) -> str | None:
    normalized = query.strip().casefold()
    if not normalized:
        return None

    exact_matches = [
        option.value
        for option in options
        if normalized in {option.value.casefold(), option.label.casefold()}
    ]
    if exact_matches:
        return exact_matches[0]

    prefix_matches = [
        option.value
        for option in options
        if option.value.casefold().startswith(normalized)
        or option.label.casefold().startswith(normalized)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    fuzzy_matches = [
        option.value for option in options if fuzzy_match(normalized, option.search_text)
    ]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    return None


async def searchable_picker(
    title: str,
    options: Sequence[SearchPickerOption],
) -> str | None:
    if not options or not supports_interactive_picker():
        return None

    session: PromptSession[str] = PromptSession(
        style=_prompt_style,
        completer=_SearchPickerCompleter(options),
        key_bindings=_build_search_picker_key_bindings(),
        bottom_toolbar=lambda: FormattedText(
            [("class:bottom-toolbar.hint", "Type to filter · Enter select · Ctrl-C cancel")]
        ),
    )

    while True:
        try:
            selection = await session.prompt_async(
                f"{title}: ",
                complete_while_typing=True,
                reserve_space_for_menu=min(max(len(options), 1), 10),
                pre_run=lambda: get_app().current_buffer.start_completion(select_first=False),
            )
        except (EOFError, KeyboardInterrupt):
            return None

        resolved = _resolve_search_picker_value(selection, options)
        if resolved is not None:
            return resolved
        if not selection.strip():
            return None
        _console.print(
            "[red]No matching selection. Keep typing to filter, or Ctrl-C to cancel.[/red]"
        )


def _cancel_search_picker(event) -> None:
    event.app.exit(exception=KeyboardInterrupt())


def _picker_move_completion(event, direction: Literal["up", "down"]) -> None:
    buffer = event.current_buffer
    if buffer.complete_state is None:
        buffer.start_completion(select_first=False)
        return
    if direction == "up":
        buffer.complete_previous()
        return
    buffer.complete_next()


def _picker_submit_value(buffer) -> str:
    complete_state = getattr(buffer, "complete_state", None)
    completions = getattr(complete_state, "completions", None)
    if completions:
        current = complete_state.current_completion or completions[0]
        return str(current.text)
    return str(buffer.text)


def _submit_search_picker(event) -> None:
    event.app.exit(result=_picker_submit_value(event.current_buffer))


def _build_search_picker_key_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-c", eager=True)
    @kb.add("escape", eager=True)
    def _cancel(event) -> None:
        _cancel_search_picker(event)

    @kb.add("up", eager=True)
    def _up_completion(event) -> None:
        _picker_move_completion(event, "up")

    @kb.add("down", eager=True)
    def _down_completion(event) -> None:
        _picker_move_completion(event, "down")

    @kb.add("enter", eager=True)
    def _submit(event) -> None:
        _submit_search_picker(event)

    return kb


def _truncate_left(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"
    return f"…{text[-(max_chars - 1) :]}"


def _truncate_right(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"
    return f"{text[: max_chars - 1]}…"


def _display_path(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path

    try:
        relative = resolved.relative_to(Path.home())
        rendered = f"~/{relative.as_posix()}"
    except ValueError:
        rendered = resolved.as_posix()

    return _truncate_left(rendered, 48)


def _git_branch_badge(path: Path) -> str | None:
    git_root = _find_git_root(path)
    if git_root is None:
        return None

    env = build_sanitized_subprocess_environment()
    try:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=2,
            env=env,
        )
        branch = branch_result.stdout.strip()
        if not branch:
            head_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=2,
                env=env,
            )
            branch = head_result.stdout.strip()
        if not branch:
            return None

        dirty_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=2,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    dirty_suffix = "*" if dirty_result.stdout.strip() else ""
    return f"[⎇ {branch}{dirty_suffix}]"


def _build_workspace_label(path: Path) -> str:
    label = _display_path(path)
    branch_badge = _git_branch_badge(path)
    if branch_badge:
        label = f"{label} {branch_badge}"
    return label


def _set_workspace_context(path: Path) -> None:
    _TOOLBAR_STATE.project_name = path.name
    _TOOLBAR_STATE.workspace_label = _build_workspace_label(path)


def _compose_toolbar_line(left: str, right: str, cols: int) -> str:
    if cols <= 0:
        return ""
    if not right:
        return _truncate_right(left, cols)
    if len(right) >= cols:
        return _truncate_right(right, cols)

    gap = 2
    max_left = max(cols - len(right) - gap, 0)
    left = _truncate_left(left, max_left)
    padding = max(cols - len(left) - len(right), gap)
    return f"{left}{' ' * padding}{right}"


def _find_instruction_file(path: Path) -> str | None:
    try:
        current = path.resolve()
    except OSError:
        current = path
    git_root = _find_git_root(current)

    for candidate_dir in (current, *current.parents):
        for filename in ("AGENTS.md", "CLAUDE.md"):
            if (candidate_dir / filename).exists():
                return filename
        if git_root is not None and candidate_dir == git_root:
            break

    return None


def _build_environment_summary(project_root: Path | None, *, agent_backend: str | None) -> Text:
    items: list[str] = []
    if project_root is not None:
        if instruction_file := _find_instruction_file(project_root):
            items.append(instruction_file)
        items.append("1 MCP server")
        items.append(f"repo {project_root.name}")
    if agent_backend:
        items.append(f"agent {agent_backend}")

    summary = " · ".join(items) if items else "chat ready"
    return Text.assemble(
        ("● ", "bold green"),
        ("Environment loaded: ", "dim"),
        (summary, "dim"),
    )


def _build_prompt_placeholder() -> FormattedText:
    if _supports_truecolor_terminal():
        muted_style = f"fg:{_REPL_COLORS['text_muted']}"
        accent_style = f"fg:{_REPL_COLORS['accent']} bold"
    else:
        muted_style = f"fg:{_ANSI_REPL_COLORS['muted']}"
        accent_style = f"fg:{_ANSI_REPL_COLORS['accent']} bold"

    return FormattedText(
        [
            (muted_style, "Type a request, "),
            (accent_style, "/"),
            (muted_style, " for commands, or "),
            (accent_style, "?"),
            (muted_style, " for shortcuts"),
        ]
    )


def _build_banner_heading(agent_backend: str | None, *, version_text: str) -> Text:
    return Text.assemble(
        ("ᘚᘛ", "bold green"),
        ("  ", ""),
        ("Kagan", "bold green"),
        (f" v{version_text}", "dim"),
        (" · ", "dim"),
        (agent_backend or "chat", "dim"),
    )


def _history_cycle_target(
    *,
    current_index: int,
    working_line_count: int,
    direction: Literal["up", "down"],
) -> int | None:
    last_history_index = working_line_count - 2
    if last_history_index < 0:
        return None
    if direction == "up":
        if current_index <= 0 or current_index > last_history_index:
            return last_history_index
        return current_index - 1
    if current_index >= last_history_index or current_index < 0:
        return 0
    return current_index + 1


def _cycle_history(event, direction: Literal["up", "down"]) -> None:
    buffer = event.current_buffer
    target = _history_cycle_target(
        current_index=buffer.working_index,
        working_line_count=len(getattr(buffer, "_working_lines", [])),
        direction=direction,
    )
    if target is None:
        return
    buffer.go_to_history(target)


def _bottom_toolbar() -> FormattedText:
    status_left = _TOOLBAR_STATE.workspace_label or _display_path(Path.cwd())
    status_right_parts: list[str] = []
    if _TOOLBAR_STATE.agent_backend:
        status_right_parts.append(_TOOLBAR_STATE.agent_backend)
    if _TOOLBAR_STATE.context_pct is not None:
        status_right_parts.append(f"ctx {_TOOLBAR_STATE.context_pct:.0%}")
    status_right_parts.append(f"{_TOOLBAR_STATE.turn_count} msg")
    if _TOOLBAR_STATE.turn_count != 1:
        status_right_parts[-1] = f"{_TOOLBAR_STATE.turn_count} msgs"
    status_right = " · ".join(status_right_parts)

    shortcut_left = _SHORTCUT_HINT_STREAMING if _TOOLBAR_STATE.is_streaming else _SHORTCUT_HINT_IDLE
    shortcut_right = f"session: {_TOOLBAR_STATE.session_label}"
    cols = shutil.get_terminal_size().columns
    rule = "─" * max(cols, 1)
    return FormattedText(
        [
            ("class:bottom-toolbar.rule", rule),
            ("", "\n"),
            ("class:bottom-toolbar.status", _compose_toolbar_line(status_left, status_right, cols)),
            ("", "\n"),
            (
                "class:bottom-toolbar.status",
                _compose_toolbar_line(shortcut_left, shortcut_right, cols),
            ),
        ]
    )


def _build_prompt_message() -> FormattedText:
    if _supports_truecolor_terminal():
        prompt_style = f"bold {_REPL_COLORS['accent']}"
    else:
        prompt_style = f"bold {_ANSI_REPL_COLORS['accent']}"
    return FormattedText([(prompt_style, "> ")])


_kb = KeyBindings()


@_kb.add("c-j")
def _ctrl_j(event) -> None:
    event.current_buffer.insert_text("\n")


@_kb.add("up")
def _up(event) -> None:
    buffer = event.current_buffer
    if buffer.complete_state is not None:
        buffer.complete_previous()
        return
    if not buffer.document.on_first_line:
        buffer.cursor_up(count=1)
        return
    _cycle_history(event, "up")


@_kb.add("down")
def _down(event) -> None:
    buffer = event.current_buffer
    if buffer.complete_state is not None:
        buffer.complete_next()
        return
    if not buffer.document.on_last_line:
        buffer.cursor_down(count=1)
        return
    _cycle_history(event, "down")


@_kb.add("c-c")
def _ctrl_c(event) -> None:
    buffer = event.current_buffer
    if not buffer.text:
        return
    line_count = len(getattr(buffer, "_working_lines", []))
    if line_count > 0:
        buffer.go_to_history(line_count - 1)
    buffer.text = ""
    buffer.cursor_position = 0


_console = Console(highlight=False)
_prompt_style = Style.from_dict(_PROMPT_STYLE_RULES)
_prompt_session: PromptSession[str] | None = None


def _get_prompt_session() -> PromptSession[str]:
    global _prompt_session
    if _prompt_session is None:
        _prompt_session = PromptSession(
            style=_prompt_style,
            completer=_SlashCompleter(),
            key_bindings=_kb,
            bottom_toolbar=_bottom_toolbar,
        )
    return _prompt_session


WAVE_FRAMES = (
    "ᘚᘚᘚᘚ",
    "ᘛᘚᘚᘚ",
    "ᘛᘛᘚᘚ",
    "ᘛᘛᘛᘚ",
    "ᘛᘛᘛᘛ",
    "ᘚᘛᘛᘛ",
    "ᘚᘚᘛᘛ",
    "ᘚᘚᘚᘛ",
)


def _write_boot_banner(
    project_root: Path | None = None, *, agent_backend: str | None = None
) -> None:
    ver = version("kagan")
    cols = shutil.get_terminal_size().columns
    panel_width = min(cols, 88) if cols >= 52 else None
    title = _build_banner_heading(agent_backend, version_text=ver)
    subtitle = Text("Describe a task to get started.", style="default")
    tip = Text.assemble(
        ("Tip: ", "dim"),
        (_BOOT_TIP_COMMAND, "bold green"),
        (f" {_BOOT_TIP_TEXT}", "dim"),
    )
    safety = Text("Review agent output before you apply it.", style="dim")

    banner = Panel(
        Group(title, subtitle, tip, safety),
        box=box.ROUNDED,
        border_style="green",
        padding=(0, 2),
        expand=False,
        width=panel_width,
    )

    _console.print()
    _console.print(banner)
    _console.print(_build_environment_summary(project_root, agent_backend=agent_backend))
    _console.print()


def _animate_connecting() -> None:
    if os.environ.get("KAGAN_CHAT_SKIP_BOOT_ANIMATION") == "1":
        _console.print(Text(WAVE_FRAMES[-1], style="dim cyan"))
        return
    for frame in WAVE_FRAMES:
        _console.print(f"\r[dim cyan]{frame}[/dim cyan]", end="")
        time.sleep(0.08)
    _console.print()


def _find_git_root(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
            env=build_sanitized_subprocess_environment(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _env_flag_enabled(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized not in {"0", "false", "no", "off"}


async def run_chat_async(
    *,
    prompt: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> str | None:
    from kagan.chat.controller import ChatController
    from kagan.core import KaganCore, resolve_default_agent_backend

    async with KaganCore() as client:
        backend = agent
        if not backend:
            settings = await client.settings.get()
            backend = resolve_default_agent_backend(settings)

        controller = ChatController(
            client,
            agent_backend=backend,
            mcp_session_id=session_id,
            prefer_session_backend=agent is None,
        )

        if not await controller.ensure_project():
            return None

        await controller.hydrate_persistent_session(explicit_session_id=session_id)

        _set_workspace_context(Path.cwd())
        _TOOLBAR_STATE.agent_backend = controller.agent_backend
        _TOOLBAR_STATE.turn_count = controller._turn_count
        _TOOLBAR_STATE.context_pct = None

        _write_boot_banner(Path.cwd(), agent_backend=controller.agent_backend)

        await controller.run(prompt=prompt)

    return None


def run_chat(
    prompt: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> str | None:
    return asyncio.run(run_chat_async(prompt=prompt, session_id=session_id, agent=agent))
