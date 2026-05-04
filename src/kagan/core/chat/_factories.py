"""Long-lived ACP factory — keeps ONE orchestrator subprocess across turns.

Counterpart to :class:`kagan.core.chat.acp.SpawnPerTurnACPFactory`. The CLI REPL
adopts this so normal turns share a connection while session switches pay a
process restart via :meth:`LongLivedACPFactory.restart`.

The factory is async-context-managed: entering spawns the subprocess, runs the
ACP ``initialize`` handshake, creates an ACP session, and writes the per-cwd
``.mcp.json`` manifest. Exiting tears down the connection and removes the
manifest. ``restart()`` runs both in sequence so callers can rebind on session
switch without re-doing the with-statement.

Permission resolution is delegated to the caller-supplied resolver via
``prompt(..., permission_resolver=...)``, identical to
``SpawnPerTurnACPFactory``. The factory contains no UI.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import acp
from acp.schema import (
    ClientCapabilities,
    Implementation,
    McpServerStdio,
)
from loguru import logger

from kagan.core.errors import AgentError

if TYPE_CHECKING:
    import os
    from collections.abc import Awaitable, Callable

    from kagan.core.chat.acp import (
        ACPTurnResult,
        PermissionDecision,
        PermissionRequestPayload,
    )

_ACP_CLIENT_NAME = "kagan"
_ACP_CLIENT_TITLE = "Kagan"
_ACP_CLIENT_VERSION = "0.1.0"
_ACP_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024


@dataclass
class LongLivedACPFactory:
    """ACP factory that maintains ONE orchestrator subprocess across many turns.

    Mirrors :class:`SpawnPerTurnACPFactory`'s ``prompt`` contract but reuses the
    underlying ACP connection between calls. ``restart()`` tears down + respawns
    in place; consumers stay alive across session switches.

    ``client`` is the :class:`KaganCore` instance; ``agent_backend`` selects the
    ACP-capable backend. ``cwd`` is the orchestrator working directory and the
    location where ``.mcp.json`` is written.
    """

    client: Any
    agent_backend: str
    cwd: str | os.PathLike[str]
    attachments: list[dict[str, str]] | None = None

    _stack: AsyncExitStack | None = field(default=None, init=False, repr=False)
    _conn: Any = field(default=None, init=False, repr=False)
    _proc: Any = field(default=None, init=False, repr=False)
    _capture: Any = field(default=None, init=False, repr=False)
    _acp_session_id: str | None = field(default=None, init=False, repr=False)
    _mcp_session_id: str | None = field(default=None, init=False, repr=False)
    _mcp_path: Path | None = field(default=None, init=False, repr=False)
    _resolved_cwd: Path | None = field(default=None, init=False, repr=False)
    _entered: bool = field(default=False, init=False, repr=False)

    # ---------------------------------------------------------------- lifecycle

    async def __aenter__(self) -> LongLivedACPFactory:
        if self._entered:
            raise RuntimeError("LongLivedACPFactory already entered")
        stack = AsyncExitStack()
        try:
            await self._spawn_and_handshake(stack)
        except BaseException:
            await stack.aclose()
            await self._cleanup_mcp_manifest()
            raise
        self._stack = stack
        self._entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        stack, self._stack = self._stack, None
        self._entered = False
        if stack is not None:
            with contextlib.suppress(Exception):
                await stack.aclose()
        await self._cleanup_mcp_manifest()
        self._conn = None
        self._proc = None
        self._capture = None
        self._acp_session_id = None
        self._mcp_session_id = None
        self._mcp_path = None
        self._resolved_cwd = None

    async def restart(self) -> None:
        """Tear down + respawn the underlying ACP connection in place."""
        await self.__aexit__(None, None, None)
        await self.__aenter__()

    # ------------------------------------------------------------------ prompt

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Callable[[PermissionRequestPayload], Awaitable[PermissionDecision]]
        | None = None,
    ) -> ACPTurnResult:
        del session_id, agent_backend  # long-lived: ACP session id is owned here

        from kagan.core.chat.acp import ACPTurnResult

        if not self._entered or self._conn is None or self._capture is None:
            raise RuntimeError("LongLivedACPFactory.prompt called before __aenter__")

        # Reset per-turn state on the long-lived capture client.
        self._capture.text_chunks = []
        self._capture._on_update = on_update  # type: ignore[attr-defined]
        self._capture._permission_resolver = permission_resolver  # type: ignore[attr-defined]

        full_blocks = await self._build_prompt_blocks(prompt_blocks)

        prompt_task = asyncio.create_task(
            self._conn.prompt(session_id=self._acp_session_id, prompt=full_blocks)
        )
        cancel_task = asyncio.create_task(cancel_event.wait())

        try:
            done, _pending = await asyncio.wait(
                {prompt_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            cancel_task.cancel()

        if cancel_task in done and not prompt_task.done():
            prompt_task.cancel()
            try:
                await prompt_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("long-lived ACP prompt raised after cancel")
            return ACPTurnResult(
                full_response="".join(self._capture.text_chunks).strip(),
                cancelled=True,
                usage=None,
            )

        try:
            prompt_task.result()
        except asyncio.CancelledError:
            return ACPTurnResult(
                full_response="".join(self._capture.text_chunks).strip(),
                cancelled=True,
                usage=None,
            )
        except (acp.RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            from kagan.core import friendly_acp_error_message

            raise AgentError(
                friendly_acp_error_message(
                    error=exc,
                    agent_backend=self.agent_backend,
                    during="prompt delivery",
                )
            ) from exc

        return ACPTurnResult(
            full_response="".join(self._capture.text_chunks).strip(),
            cancelled=False,
            usage=None,
        )

    # ---------------------------------------------------------------- internal

    async def _spawn_and_handshake(self, stack: AsyncExitStack) -> None:
        from kagan.cli.chat.acp import (
            _CaptureACPClient,
            _resolve_acp_command_for_backend,
        )
        from kagan.core import (
            build_agent_environment,
            build_mcp_manifest,
            default_db_path,
            friendly_acp_error_message,
            get_backend_spec,
        )
        from kagan.core._subprocess import resolve_spawn_command

        exe, exe_args = _resolve_acp_command_for_backend(self.agent_backend)
        resolved_cmd = resolve_spawn_command(exe, *exe_args)

        mcp_session_id = uuid4().hex[:16]
        db_path = str(default_db_path())
        resolved_cwd = Path(self.cwd)
        mcp_path = resolved_cwd / ".mcp.json"

        mcp_content = build_mcp_manifest(
            session_id=mcp_session_id,
            db_path=db_path,
            role="ORCHESTRATOR",
            project_id=self.client.active_project_id,
        )
        await asyncio.to_thread(mcp_path.write_text, mcp_content, "utf-8")

        backend = get_backend_spec(self.agent_backend)
        env = build_agent_environment(
            session_id=mcp_session_id,
            task_id=None,
            backend_env_vars=backend.env_vars,
        )

        from kagan.core import acp_handshake_timeout_seconds

        capture = _CaptureACPClient(on_update=None, permission_resolver=None)
        timeout_s = acp_handshake_timeout_seconds(self.agent_backend)

        try:
            conn, proc = await stack.enter_async_context(
                acp.spawn_agent_process(
                    capture,
                    resolved_cmd[0],
                    *resolved_cmd[1:],
                    cwd=str(resolved_cwd),
                    env=env,
                    transport_kwargs={"limit": _ACP_STDIO_BUFFER_LIMIT_BYTES},
                )
            )
        except (acp.RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            raise AgentError(
                friendly_acp_error_message(
                    error=exc, agent_backend=self.agent_backend, during="handshake"
                )
            ) from exc

        await self._do_initialize(conn, proc, timeout_s)
        sess = await self._do_new_session(
            conn, proc, timeout_s, resolved_cwd, mcp_session_id, db_path
        )

        self._conn = conn
        self._proc = proc
        self._capture = capture
        self._acp_session_id = sess.session_id
        self._mcp_session_id = mcp_session_id
        self._mcp_path = mcp_path
        self._resolved_cwd = resolved_cwd

    async def _do_initialize(self, conn: Any, proc: Any, timeout_s: float) -> None:
        from kagan.cli.chat.acp import _acp_process_exit_message
        from kagan.core import (
            ACP_TIMEOUT_HINT,
            acp_process_exit_hint,
            friendly_acp_error_message,
        )

        try:
            await asyncio.wait_for(
                conn.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=ClientCapabilities(terminal=False),
                    client_info=Implementation(
                        name=_ACP_CLIENT_NAME,
                        title=_ACP_CLIENT_TITLE,
                        version=_ACP_CLIENT_VERSION,
                    ),
                ),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            early_exit = await _acp_process_exit_message(
                self.agent_backend, proc, during="initialize"
            )
            if early_exit is not None:
                raise AgentError(early_exit) from exc
            raise AgentError(
                f"{self.agent_backend} initialization timed out after {timeout_s:.0f}s "
                f"during ACP initialize. {ACP_TIMEOUT_HINT}"
            ) from exc
        except (acp.RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            hint = acp_process_exit_hint(agent_backend=self.agent_backend, details=str(exc))
            message = friendly_acp_error_message(
                error=exc, agent_backend=self.agent_backend, during="initialize"
            )
            if hint:
                message = f"{message} {hint}"
            raise AgentError(message) from exc

    async def _do_new_session(
        self,
        conn: Any,
        proc: Any,
        timeout_s: float,
        resolved_cwd: Path,
        mcp_session_id: str,
        db_path: str,
    ) -> Any:
        from kagan.cli.chat.acp import _acp_process_exit_message, _new_session_with_mcp_fallback
        from kagan.core import ACP_TIMEOUT_HINT

        mcp_servers: list[Any] = [
            McpServerStdio(
                name="kagan",
                command="kagan",
                args=[
                    "mcp",
                    "--session-id",
                    mcp_session_id,
                    "--db",
                    db_path,
                    "--admin",
                    *(
                        ["--project-id", self.client.active_project_id]
                        if self.client.active_project_id
                        else []
                    ),
                ],
                env=[],
            )
        ]
        try:
            return await _new_session_with_mcp_fallback(
                conn,
                cwd=str(resolved_cwd),
                mcp_servers=mcp_servers,
                timeout_s=timeout_s,
                agent_backend=self.agent_backend,
            )
        except TimeoutError as exc:
            early_exit = await _acp_process_exit_message(
                self.agent_backend, proc, during="session creation"
            )
            if early_exit is not None:
                raise AgentError(early_exit) from exc
            raise AgentError(
                f"{self.agent_backend} initialization timed out after {timeout_s:.0f}s "
                f"during ACP session creation. {ACP_TIMEOUT_HINT}"
            ) from exc

    async def _build_prompt_blocks(self, prompt_blocks: list[Any]) -> list[Any]:
        """Wrap user prompt blocks with the orchestrator system prompt + attachments.

        Mirrors ``run_orchestrator_turn``'s non-lightweight prompt assembly.
        Engine callers pass plain ``TextContentBlock`` user blocks; we prepend
        the resolved orchestrator system prompt and append any image/text
        attachments configured on the factory.
        """
        from kagan.cli.chat.prompt import _format_user_request_block
        from kagan.core import resolve_orchestrator_prompt

        settings = await self.client.settings.get()
        cwd = self._resolved_cwd or Path(self.cwd)
        system_prompt = resolve_orchestrator_prompt(settings, cwd)

        user_text_parts: list[str] = []
        passthrough: list[Any] = []
        for block in prompt_blocks:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                user_text_parts.append(text)
            else:
                passthrough.append(block)
        user_text = "\n\n".join(user_text_parts)

        out: list[Any] = [
            acp.text_block(system_prompt),
            acp.text_block(_format_user_request_block(user_text)),
        ]
        out.extend(passthrough)
        for att in self.attachments or []:
            if att.get("type") == "image":
                out.append(acp.image_block(data=att["data"], mime_type=att["mime_type"]))
            else:
                out.append(acp.text_block(f"--- {att['name']} ---\n{att['data']}"))
        return out

    async def _cleanup_mcp_manifest(self) -> None:
        path = self._mcp_path
        if path is None:
            return
        try:
            if path.exists():
                await asyncio.to_thread(path.unlink)
        except OSError:
            logger.debug("Failed to remove MCP manifest at {}", path)


__all__ = ["LongLivedACPFactory"]
