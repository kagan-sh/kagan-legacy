import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from kagan.core._agent import BackendCapability, BackendSpec
from kagan.core._sessions import Sessions
from kagan.core.enums import TaskStatus

pytestmark = [pytest.mark.unit]


class _FakeEvents:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, Any, dict[str, Any], str | None, bool]] = []

    async def emit(
        self,
        task_id: str,
        event_type: Any,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        persist: bool = True,
    ) -> None:
        self.emitted.append((task_id, event_type, payload, session_id, persist))

    def publish_board(self, event: Any) -> None:
        pass

    def notify_agent_end_handled(self, session_id: str) -> None:
        pass

    def register_agent_end_subscriber(self, session_id: str, count: int = 1) -> None:
        pass


async def _stub_get_task(_task_id: str) -> Any:
    raise AssertionError("_get_task should not run in this shutdown path")


def _stub_set_status(_task_id: str, _status: Any) -> Any:
    raise AssertionError("_set_status should not run in this shutdown path")


async def _stub_ensure_workspace(_task_id: str) -> Any:
    raise AssertionError("_ensure_workspace should not run in this shutdown path")


async def test_handle_acp_done_ignores_executor_shutdown_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    async def fake_to_thread(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Executor shutdown has been called")

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)

    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task

    await sessions._handle_acp_done(done_task, "task-1", "session-1")
    assert events.emitted == []


async def test_make_acp_callback_emits_output_chunks_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OUTPUT_CHUNK events must not be persisted to avoid DB bloat."""
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    monkeypatch.setattr(
        "kagan.core._acp.map_acp_update_to_event",
        lambda _update: ("output_chunk", {"text": "hello"}),
    )

    callback = sessions._make_acp_callback("task-1", "session-1")
    await callback("acp-session-1", object())

    assert events.emitted == [("task-1", "output_chunk", {"text": "hello"}, "session-1", False)]


async def test_handle_acp_done_reraises_unrelated_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    async def fake_to_thread(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("unexpected runtime failure")

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)

    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task

    with pytest.raises(RuntimeError, match="unexpected runtime failure"):
        await sessions._handle_acp_done(done_task, "task-2", "session-2")


async def test_run_uses_backend_spec_capability_for_detached_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    task = SimpleNamespace(
        id="task-1",
        title="Task title",
        description="Task description",
        acceptance_criteria=[],
        project_id="project-1",
        status=TaskStatus.BACKLOG,
    )
    worktree = SimpleNamespace(worktree_path="/tmp/worktree")
    session_obj = SimpleNamespace(id="session-1")
    backend_calls: list[str] = []
    spawn_calls: list[tuple[str, str, str, str]] = []
    created_coroutines: list[Any] = []
    updated_pids: list[tuple[str, int]] = []

    async def fake_prepare_session(*_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]:
        return task, worktree, session_obj

    async def fake_fetch_project_learnings(_self: Any, _project_id: str) -> list[str]:
        return []

    def fake_get_backend_spec(name: str) -> BackendSpec:
        backend_calls.append(name)
        return BackendSpec(
            name=name,
            executable="codex",
            supports_acp=True,
            capabilities=frozenset({BackendCapability.ACP_STREAMING}),
        )

    class _FakeReaderTask:
        def add_done_callback(self, callback: Any) -> None:
            callback(SimpleNamespace())

    async def fake_spawn_agent_via_acp(
        backend_name: str,
        worktree_path: Any,
        prompt: str,
        *,
        session_id: str,
        task_id: str,
        db_path: str,
        project_id: str | None = None,
        on_session_update: Any,
        on_permission_grant: Any = None,
    ) -> tuple[int, Any]:
        del worktree_path, prompt, on_session_update, on_permission_grant, project_id
        spawn_calls.append((backend_name, session_id, task_id, db_path))
        return 4242, _FakeReaderTask()

    def fake_create_task(coro: Any, *, name: str | None = None) -> Any:
        del name
        created_coroutines.append(coro)
        coro.close()
        return SimpleNamespace(add_done_callback=lambda _cb: None)

    monkeypatch.setattr("kagan.core._sessions.Sessions._prepare_session", fake_prepare_session)
    monkeypatch.setattr(
        "kagan.core._sessions.Sessions._fetch_project_learnings", fake_fetch_project_learnings
    )
    monkeypatch.setattr("kagan.core._sessions.get_backend_spec", fake_get_backend_spec)
    monkeypatch.setattr("kagan.core._sessions.spawn_agent_via_acp", fake_spawn_agent_via_acp)
    monkeypatch.setattr(
        "kagan.core._sessions.spawn_agent",
        lambda *args, **kwargs: pytest.fail("spawn_agent should not be called"),
    )
    monkeypatch.setattr("kagan.core._sessions.asyncio.create_task", fake_create_task)

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "kagan.core._sessions._db_async",
        lambda *_args, **_kwargs: asyncio.sleep(0, result={"default_agent_backend": "codex"}),
    )
    monkeypatch.setattr("kagan.core._sessions.default_db_path", lambda: "/tmp/kagan.db")
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_task_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_review_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr("kagan.core._sessions.get_persona_prompt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("kagan.core._sessions.build_persona_section", lambda prompt: prompt)

    async def fake_update_session_pid(session_id: str, pid: int) -> None:
        updated_pids.append((session_id, pid))

    monkeypatch.setattr(sessions, "_update_session_pid", fake_update_session_pid)
    monkeypatch.setattr(
        sessions, "_make_acp_callback", lambda *_args, **_kwargs: (lambda *_a, **_k: None)
    )
    monkeypatch.setattr(sessions, "_handle_acp_done", lambda *_args, **_kwargs: asyncio.sleep(0))

    result = await sessions.run("task-1", agent_backend="codex")

    assert result is session_obj
    assert backend_calls == ["codex"]
    assert spawn_calls == [("codex", "session-1", "task-1", "/tmp/kagan.db")]
    assert updated_pids == [("session-1", 4242)]
    assert len(created_coroutines) == 1


async def test_run_parses_float_timeout_for_non_acp_detached_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    task = SimpleNamespace(
        id="task-timeout",
        title="Task title",
        description="Task description",
        acceptance_criteria=[],
        project_id="project-1",
        status=TaskStatus.BACKLOG,
    )
    worktree = SimpleNamespace(worktree_path="/tmp/worktree")
    session_obj = SimpleNamespace(id="session-timeout")
    spawn_calls: list[dict[str, Any]] = []
    updated_pids: list[tuple[str, int]] = []

    async def fake_prepare_session(*_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]:
        return task, worktree, session_obj

    async def fake_fetch_project_learnings(_self: Any, _project_id: str) -> list[str]:
        return []

    def fake_get_backend_spec(name: str) -> BackendSpec:
        return BackendSpec(name=name, executable="codex", supports_acp=False)

    async def fake_spawn_agent(
        backend_name: str,
        worktree_path: Any,
        prompt: str,
        *,
        session_id: str,
        task_id: str,
        db_path: str,
        project_id: str | None = None,
        timeout_seconds: int,
    ) -> int:
        del worktree_path, prompt, project_id
        spawn_calls.append(
            {
                "backend_name": backend_name,
                "session_id": session_id,
                "task_id": task_id,
                "db_path": db_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        return 5150

    def fake_create_task(coro: Any, *, name: str | None = None) -> Any:
        del name
        coro.close()
        return SimpleNamespace(add_done_callback=lambda _cb: None)

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    monkeypatch.setattr("kagan.core._sessions.Sessions._prepare_session", fake_prepare_session)
    monkeypatch.setattr(
        "kagan.core._sessions.Sessions._fetch_project_learnings", fake_fetch_project_learnings
    )
    monkeypatch.setattr("kagan.core._sessions.get_backend_spec", fake_get_backend_spec)
    monkeypatch.setattr("kagan.core._sessions.spawn_agent", fake_spawn_agent)
    monkeypatch.setattr(
        "kagan.core._sessions.spawn_agent_via_acp",
        lambda *args, **kwargs: pytest.fail("spawn_agent_via_acp should not be called"),
    )
    monkeypatch.setattr("kagan.core._sessions.asyncio.create_task", fake_create_task)
    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "kagan.core._sessions._db_async",
        lambda *_args, **_kwargs: asyncio.sleep(
            0,
            result={
                "default_agent_backend": "codex",
                "agent_timeout_seconds": "60.5",
            },
        ),
    )
    monkeypatch.setattr("kagan.core._sessions.default_db_path", lambda: "/tmp/kagan.db")
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_task_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_review_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr("kagan.core._sessions.get_persona_prompt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("kagan.core._sessions.build_persona_section", lambda prompt: prompt)

    async def fake_update_session_pid(session_id: str, pid: int) -> None:
        updated_pids.append((session_id, pid))

    monkeypatch.setattr(sessions, "_update_session_pid", fake_update_session_pid)

    result = await sessions.run("task-timeout", agent_backend="codex")

    assert result is session_obj
    assert spawn_calls == [
        {
            "backend_name": "codex",
            "session_id": "session-timeout",
            "task_id": "task-timeout",
            "db_path": "/tmp/kagan.db",
            "timeout_seconds": 60,
        }
    ]
    assert updated_pids == [("session-timeout", 5150)]


async def test_run_uses_backend_spec_executable_for_attached_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    task = SimpleNamespace(
        id="task-2",
        title="Task title",
        description="Task description",
        acceptance_criteria=[],
        project_id="project-1",
        status=TaskStatus.BACKLOG,
    )
    worktree = SimpleNamespace(worktree_path="/tmp/worktree")
    session_obj = SimpleNamespace(id="session-2")
    backend_calls: list[str] = []
    launch_calls: list[dict[str, Any]] = []

    async def fake_prepare_session(*_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]:
        return task, worktree, session_obj

    def fake_get_backend_spec(name: str) -> BackendSpec:
        backend_calls.append(name)
        return BackendSpec(name=name, executable="codex")

    async def fake_launcher(**kwargs: Any) -> None:
        launch_calls.append(kwargs)

    monkeypatch.setattr("kagan.core._sessions.Sessions._prepare_session", fake_prepare_session)
    monkeypatch.setattr("kagan.core._sessions.get_backend_spec", fake_get_backend_spec)
    monkeypatch.setattr("kagan.core._sessions.get_launcher", lambda _name: fake_launcher)

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "kagan.core._sessions._db_async",
        lambda *_args, **_kwargs: asyncio.sleep(0, result={"default_agent_backend": "codex"}),
    )
    monkeypatch.setattr("kagan.core._sessions.default_db_path", lambda: "/tmp/kagan.db")
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_task_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr(
        "kagan.core._sessions.resolve_review_prompt", lambda *_args, **_kwargs: "prompt"
    )
    monkeypatch.setattr("kagan.core._sessions.get_persona_prompt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("kagan.core._sessions.build_persona_section", lambda prompt: prompt)
    monkeypatch.setattr(
        "kagan.core._sessions.build_attached_startup_prompt",
        lambda _task, _criteria=None: "prompt",
    )

    async def fake_mark_session_running(session_id: str) -> None:
        pass

    monkeypatch.setattr(sessions, "_mark_session_running", fake_mark_session_running)

    result = await sessions.run("task-2", agent_backend="codex", launcher="vscode")

    assert result is session_obj
    assert backend_calls == ["codex"]
    assert launch_calls == [
        {
            "worktree_path": Path(worktree.worktree_path),
            "session_id": "session-2",
            "agent_cmd": "codex",
            "agent_backend": "codex",
            "db_path": "/tmp/kagan.db",
            "startup_prompt": "prompt",
            "task_id": "task-2",
        }
    ]


async def test_should_retry_runs_success_command_via_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    task = SimpleNamespace(
        id="task-retry",
        success_command="ruff check && pytest -q",
        max_retries=2,
        agent_backend="codex",
    )
    db_results = iter(
        [
            SimpleNamespace(attempt=1, persona="planner"),
            SimpleNamespace(worktree_path="/tmp/retry-task"),
            {},
            None,
        ]
    )
    reruns: list[tuple[str, str | None, str | None]] = []
    status_updates: list[tuple[str, TaskStatus]] = []
    shell_call: dict[str, Any] = {}

    async def fake_db_async(*_args: Any, **_kwargs: Any) -> Any:
        return next(db_results)

    class _FailingProc:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"check failed"

        def kill(self) -> None:
            return None

        async def wait(self) -> None:
            return None

    async def fake_create_subprocess_shell(command: str, **kwargs: Any) -> _FailingProc:
        shell_call["command"] = command
        shell_call["kwargs"] = kwargs
        return _FailingProc()

    async def fake_run(
        task_id: str,
        *,
        agent_backend: str | None = None,
        persona: str | None = None,
    ) -> Any:
        reruns.append((task_id, agent_backend, persona))
        return SimpleNamespace(id="session-retry-2")

    def fake_set_status(task_id: str, status: TaskStatus) -> None:
        status_updates.append((task_id, status))

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    monkeypatch.setattr("kagan.core._sessions._db_async", fake_db_async)
    monkeypatch.setattr(
        "kagan.core._sessions.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )
    monkeypatch.setattr(
        "kagan.core._sessions.asyncio.create_subprocess_exec",
        lambda *_args, **_kwargs: pytest.fail(
            "create_subprocess_exec should not be used for success_command"
        ),
    )
    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(sessions, "run", fake_run)
    monkeypatch.setattr(sessions, "_set_status", fake_set_status)

    should_retry = await sessions._should_retry(task, "session-retry-1")

    assert should_retry is True
    assert shell_call["command"] == "ruff check && pytest -q"
    assert shell_call["kwargs"]["cwd"] == Path("/tmp/retry-task")
    assert status_updates == [("task-retry", TaskStatus.BACKLOG)]
    assert reruns == [("task-retry", "codex", "planner")]
    assert events.emitted == [
        (
            "task-retry",
            "task_status_changed",
            {"from": TaskStatus.IN_PROGRESS.value, "to": TaskStatus.BACKLOG.value},
            "session-retry-1",
            True,
        )
    ]
