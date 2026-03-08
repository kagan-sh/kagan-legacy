import inspect
from dataclasses import dataclass
from functools import partial
from typing import Any

from textual.command import DiscoveryHit, Hit, Hits, Provider

from kagan.core.enums import TaskStatus


@dataclass(frozen=True, slots=True)
class TaskScreenCommandSpec:
    command: str
    help: str
    action: str
    requires_review: bool = False


TASK_SCREEN_COMMANDS: tuple[TaskScreenCommandSpec, ...] = (
    TaskScreenCommandSpec(
        "review.ai",
        "Run AI review (advisory)",
        "run_review",
        requires_review=True,
    ),
)


def _run_screen_action(screen: Any, action: str) -> None:
    action_method = getattr(screen, f"action_{action}", None)
    if action_method is None:
        return
    result = action_method()
    if inspect.isawaitable(result):
        screen.run_worker(result)


def _command_available(screen: Any, item: TaskScreenCommandSpec) -> bool:
    if not item.requires_review:
        return True
    task = getattr(screen, "_task_model", None)
    if task is None:
        return False
    return task.status is TaskStatus.REVIEW


class TaskScreenCommandProvider(Provider):
    async def search(self, query: str) -> Hits:
        screen = self.screen
        matcher = self.matcher(query)
        for item in TASK_SCREEN_COMMANDS:
            if not _command_available(screen, item):
                continue
            score = matcher.match(item.command)
            if score <= 0:
                continue
            yield Hit(
                score,
                matcher.highlight(item.command),
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )

    async def discover(self) -> Hits:
        screen = self.screen
        for item in TASK_SCREEN_COMMANDS:
            if not _command_available(screen, item):
                continue
            yield DiscoveryHit(
                item.command,
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )
