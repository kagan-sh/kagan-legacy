"""Notify the human on the five attention events only (TUI-NOTIFY-01/02/03, P12)."""

import asyncio
import shutil
import sys
from enum import StrEnum

import httpx
from loguru import logger

from kagan.core.models import Task  # noqa: TC001 — no `from __future__ import annotations`

_TITLES = {
    "needs_you": "Kagan — task needs you",
    "review": "Kagan — task ready for review",
    "finished": "Kagan — task finished",
    "drift": "Kagan — drift detected",
    "ci_failed": "Kagan — remote CI failed",
}


class NotificationEvent(StrEnum):
    NEEDS_YOU = "needs_you"
    REVIEW = "review"
    FINISHED = "finished"
    DRIFT = "drift"
    CI_FAILED = "ci_failed"


class Notifier:
    def __init__(self, *, bell: bool = True, webhook_url: str | None = None) -> None:
        self.bell = bell
        self.webhook_url = webhook_url

    async def notify(self, event: NotificationEvent, task: Task) -> None:
        title = _TITLES[event.value]
        body = f"{task.id}: {task.title}"
        await self._os_notify(title, body)
        if self.bell:
            sys.stderr.write("\a")
        if self.webhook_url:
            await self._webhook(self.webhook_url, event, task, title, body)

    async def _os_notify(self, title: str, body: str) -> None:
        # P12: probe the binary, no-op if absent, never block a gate on notify.
        if sys.platform == "darwin" and shutil.which("osascript"):
            # P12 SECURITY: pass title/body as osascript args, NOT interpolated into -e.
            cmd = [
                "osascript",
                "-e",
                "on run {b, t}",
                "-e",
                "display notification b with title t",
                "-e",
                "end run",
                body,
                title,
            ]
        elif sys.platform.startswith("linux") and shutil.which("notify-send"):
            cmd = ["notify-send", title, body]
        else:
            logger.debug("OS notifications unavailable on {}", sys.platform)
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except FileNotFoundError:
            logger.debug("notifier binary vanished between probe and exec: {}", cmd[0])

    async def _webhook(
        self, url: str, event: NotificationEvent, task: Task, title: str, body: str
    ) -> None:
        payload = {"event": event.value, "task_id": task.id, "title": title, "body": body}
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=10.0)
        except Exception as exc:
            logger.warning("webhook delivery failed: {}", exc)
