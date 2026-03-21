"""Console setup, REPL banner, wave animation, git helpers, and entry points."""

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console
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
        "completion-menu": "bg:default fg:default",
        "completion-menu.completion.current": "noreverse bg:ansigreen fg:ansiblack bold",
        "selected-text": "noreverse bg:ansigreen fg:ansiblack",
    }


_PROMPT_STYLE_RULES: Final[dict[str, str]] = _build_prompt_style_rules()


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
    left_parts: list[str] = []
    if _TOOLBAR_STATE.session_label:
        left_parts.append(f"session: {_TOOLBAR_STATE.session_label}")
    if _TOOLBAR_STATE.agent_backend:
        left_parts.append(f"agent: {_TOOLBAR_STATE.agent_backend}")
    left_parts.append(f"turns: {_TOOLBAR_STATE.turn_count}")
    if _TOOLBAR_STATE.context_pct is not None:
        left_parts.append(f"ctx {_TOOLBAR_STATE.context_pct:.0%}")
    left = " · ".join(left_parts)
    right = "Ctrl-C clear · Ctrl-D exit"
    cols = shutil.get_terminal_size().columns
    padding = max(cols - len(left) - len(right), 2)
    return FormattedText([("", left + " " * padding + right)])


def _build_prompt_message() -> FormattedText:
    project = Path.cwd().name
    if _supports_truecolor_terminal():
        user_style = f"bold {_REPL_COLORS['accent']}"
        at_style = _REPL_COLORS["text_muted"]
        project_style = _REPL_COLORS["primary"]
    else:
        user_style = f"bold {_ANSI_REPL_COLORS['accent']}"
        at_style = _ANSI_REPL_COLORS["muted"]
        project_style = _ANSI_REPL_COLORS["primary"]
    return FormattedText(
        [
            (user_style, "kg"),
            (at_style, "@"),
            (project_style, project),
            ("", " \u203a "),
        ]
    )


_kb = KeyBindings()


@_kb.add("escape", "enter")
def _alt_enter(event) -> None:
    event.current_buffer.insert_text("\n")


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


_BRAND_SIGIL: Final[str] = "ᘚᘛ"  # mirrored wave pair — matches docs/TUI logo


def _write_boot_banner(
    project_root: Path | None = None, *, agent_backend: str | None = None
) -> None:
    ver = version("kagan")
    line1 = Text.assemble(
        (_BRAND_SIGIL, "bold green"),
        (" kagan", "bold green"),
        (f" v{ver}", "dim"),
        (" · ", "dim"),
        (agent_backend or "chat", "dim"),
    )
    project = project_root.name if project_root else None
    pad = " " * (len(_BRAND_SIGIL) + 1)
    line2 = Text.assemble(
        (pad, ""),
        (f"project: {project}", "dim") if project else ("", ""),
        (" · ", "dim") if project else ("", ""),
        ("/help for commands", "dim"),
    )
    _console.print()
    _console.print(line1)
    _console.print(line2)
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
    from kagan.chat.agents import resolve_default_agent_backend
    from kagan.chat.controller import ChatController
    from kagan.core import KaganCore

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

        _write_boot_banner(Path.cwd(), agent_backend=controller.agent_backend)

        await controller.run(prompt=prompt)

    return None


def run_chat(
    prompt: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> str | None:
    return asyncio.run(run_chat_async(prompt=prompt, session_id=session_id, agent=agent))
