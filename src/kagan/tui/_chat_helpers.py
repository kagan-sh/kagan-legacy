import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kagan.cli.chat import merge_task_follow_up_description, resolve_default_agent_backend
from kagan.core.errors import KaganError
from kagan.core.models import Task

if TYPE_CHECKING:
    from kagan.core.client import KaganCore
    from kagan.tui.widgets.chat import ChatPanel


def _default_task_session_options(task: Task) -> list[tuple[str, str]]:
    ticket = task.title.strip() or f"Ticket #{task.id[:8]}"
    return [
        (f"{ticket} · Worker", "task-worker"),
        (f"{ticket} · Reviewer", "task-reviewer"),
    ]


def build_session_options(
    core: Any,
    task: Task | list[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    options = [*core.orchestrator_sessions.options()]
    if task is None:
        return options
    if isinstance(task, Task):
        return [*options, *_default_task_session_options(task)]
    return [*options, *task]


@dataclass(slots=True)
class TitleGenerationSession:
    orchestrator_sessions: Any
    panel: "ChatPanel"
    user_message: str
    history: list[tuple[str, str]]
    session_options: list[tuple[str, str]]
    is_mounted: Callable[[], bool] | None = None


async def kick_title_generation(session: TitleGenerationSession, core: "KaganCore") -> None:
    if not session.history:
        return
    assistant_reply = session.history[-1][1] if session.history[-1][0] == "assistant" else ""
    try:
        backend = session.panel.preferred_agent_backend() or resolve_default_agent_backend(
            await core.settings.get()
        )
        title = await session.orchestrator_sessions.generate_title(
            user_message=session.user_message,
            assistant_reply=assistant_reply,
            agent_backend=backend,
        )
        mounted = session.is_mounted() if session.is_mounted is not None else True
        if title and mounted:
            active_key = session.orchestrator_sessions.active_key()
            session.panel.set_sessions(session.session_options, active_key)
    except Exception:
        return


async def send_task_message(
    core: "KaganCore",
    task: Task,
    message: str,
) -> Task:
    with contextlib.suppress(KaganError, OSError, RuntimeError):
        await core.tasks.cancel(task.id)
    description = merge_task_follow_up_description(task.description, message)
    return await core.tasks.update(task.id, description=description)
