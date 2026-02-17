"""Unit tests for the @expose metadata decorator."""

from __future__ import annotations

import inspect

from kagan.core.policy import EXPOSE_ATTR, ExposeMetadata, collect_exposed_methods, expose


class TestExposeDecorator:
    """Tests that @expose attaches correct metadata to functions."""

    def test_expose_attaches_metadata(self) -> None:
        @expose("tasks", "get", description="Get task.")
        async def get_task(task_id: str) -> None: ...

        meta = getattr(get_task, EXPOSE_ATTR, None)
        assert meta is not None
        assert isinstance(meta, ExposeMetadata)

    def test_expose_metadata_fields_are_correct(self) -> None:
        @expose(
            "review",
            "approve",
            profile="operator",
            mutating=True,
            description="Approve a review.",
        )
        async def approve_task(task_id: str) -> None: ...

        meta: ExposeMetadata = getattr(approve_task, EXPOSE_ATTR)
        assert meta.capability == "review"
        assert meta.method == "approve"
        assert meta.profile == "operator"
        assert meta.mutating is True
        assert meta.description == "Approve a review."

    def test_expose_defaults(self) -> None:
        @expose("audit", "list")
        async def list_events() -> None: ...

        meta: ExposeMetadata = getattr(list_events, EXPOSE_ATTR)
        assert meta.profile == "viewer"
        assert meta.mutating is False
        assert meta.description == ""

    def test_undecorated_method_has_no_expose_attr(self) -> None:
        async def plain_method() -> None: ...

        assert not hasattr(plain_method, EXPOSE_ATTR)

    def test_expose_preserves_original_function(self) -> None:
        @expose("tasks", "create", mutating=True)
        async def create_task(title: str) -> str: ...

        assert create_task.__name__ == "create_task"
        assert callable(create_task)

    def test_expose_metadata_is_frozen(self) -> None:
        @expose("tasks", "get")
        async def get_task() -> None: ...

        meta: ExposeMetadata = getattr(get_task, EXPOSE_ATTR)
        try:
            meta.capability = "projects"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass


class TestCollectExposedMethods:
    """Tests for collect_exposed_methods helper."""

    def test_collects_decorated_methods(self) -> None:
        class FakeApi:
            @expose("tasks", "get")
            async def get_task(self, task_id: str) -> None: ...

            @expose("tasks", "list")
            async def list_tasks(self) -> None: ...

            async def plain_method(self) -> None: ...

        api = FakeApi()
        results = collect_exposed_methods(api)
        names = [name for name, _method, _meta in results]
        assert "get_task" in names
        assert "list_tasks" in names
        assert "plain_method" not in names
        assert len(results) == 2

    def test_skips_private_methods(self) -> None:
        class FakeApi:
            @expose("tasks", "internal")
            async def _private(self) -> None: ...

        api = FakeApi()
        results = collect_exposed_methods(api)
        assert len(results) == 0

    def test_empty_object_returns_empty(self) -> None:
        results = collect_exposed_methods(object())
        assert results == []


class TestApiExposeIntegration:
    """Verify that the real KaganAPI has @expose decorators applied."""

    def test_api_exposed_inventory_contract_is_locked(self) -> None:
        from kagan.core.api import KaganAPI

        # Collect from the class itself (unbound methods still carry the attr).
        exposed = []
        for name in dir(KaganAPI):
            if name.startswith("_"):
                continue
            attr = getattr(KaganAPI, name, None)
            meta = getattr(attr, EXPOSE_ATTR, None)
            if meta is None:
                continue
            sig = inspect.signature(attr)
            params = tuple(
                (
                    param.name,
                    param.kind.name,
                    param.default is not inspect.Signature.empty,
                )
                for param in sig.parameters.values()
            )
            exposed.append(
                (
                    f"{meta.capability}.{meta.method}",
                    name,
                    params,
                    str(sig.return_annotation),
                    meta.profile,
                    meta.mutating,
                    meta.description,
                )
            )

        assert sorted(exposed) == [
            (
                "audit.list",
                "list_audit_events",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("capability", "KEYWORD_ONLY", True),
                    ("limit", "KEYWORD_ONLY", True),
                    ("cursor", "KEYWORD_ONLY", True),
                ),
                "list[AuditEvent]",
                "viewer",
                False,
                "List recent audit events.",
            ),
            (
                "diagnostics.instrumentation",
                "get_instrumentation",
                (("self", "POSITIONAL_OR_KEYWORD", False),),
                "dict[str, Any]",
                "maintainer",
                False,
                "Return in-memory instrumentation aggregates.",
            ),
            (
                "projects.add_repo",
                "add_repo",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("project_id", "POSITIONAL_OR_KEYWORD", False),
                    ("repo_path", "POSITIONAL_OR_KEYWORD", False),
                    ("is_primary", "KEYWORD_ONLY", True),
                ),
                "str",
                "maintainer",
                True,
                "Add a repository to a project.",
            ),
            (
                "projects.create",
                "create_project",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("name", "POSITIONAL_OR_KEYWORD", False),
                    ("description", "KEYWORD_ONLY", True),
                    ("repo_paths", "KEYWORD_ONLY", True),
                ),
                "str",
                "maintainer",
                True,
                "Create a new project with optional repositories.",
            ),
            (
                "projects.find_by_repo_path",
                "find_project_by_repo_path",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("repo_path", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Project | None",
                "viewer",
                False,
                "Find a project containing the given repository path.",
            ),
            (
                "projects.get",
                "get_project",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("project_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Project | None",
                "viewer",
                False,
                "Get a project by ID.",
            ),
            (
                "projects.list",
                "list_projects",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("limit", "KEYWORD_ONLY", True),
                ),
                "list[Project]",
                "viewer",
                False,
                "List recent projects.",
            ),
            (
                "projects.open",
                "open_project",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("project_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Project",
                "maintainer",
                True,
                "Open/switch to a project.",
            ),
            (
                "projects.repos",
                "get_project_repos",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("project_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "list[Repo]",
                "viewer",
                False,
                "Get all repos for a project.",
            ),
            (
                "review.approve",
                "approve_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Task | None",
                "operator",
                True,
                "Approve a task review.",
            ),
            (
                "review.reject",
                "reject_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("feedback", "POSITIONAL_OR_KEYWORD", True),
                    ("action", "POSITIONAL_OR_KEYWORD", True),
                ),
                "Task | None",
                "operator",
                True,
                "Reject a task review with feedback.",
            ),
            (
                "review.request",
                "request_review",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("summary", "POSITIONAL_OR_KEYWORD", True),
                ),
                "Task | None",
                "pair_worker",
                True,
                "Mark task ready for review.",
            ),
            (
                "settings.get",
                "get_settings",
                (("self", "POSITIONAL_OR_KEYWORD", False),),
                "dict[str, object]",
                "maintainer",
                False,
                "Get admin-exposed settings.",
            ),
            (
                "settings.update",
                "update_settings",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("fields", "POSITIONAL_OR_KEYWORD", False),
                ),
                "tuple[bool, str, dict[str, object]]",
                "maintainer",
                True,
                "Update allowlisted settings fields.",
            ),
            (
                "tasks.context",
                "get_task_context",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "dict[str, Any]",
                "viewer",
                False,
                "Get task context for AI tools.",
            ),
            (
                "tasks.create",
                "create_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("title", "POSITIONAL_OR_KEYWORD", False),
                    ("description", "POSITIONAL_OR_KEYWORD", True),
                    ("project_id", "KEYWORD_ONLY", True),
                    ("created_by", "KEYWORD_ONLY", True),
                    ("status", "KEYWORD_ONLY", True),
                    ("priority", "KEYWORD_ONLY", True),
                    ("task_type", "KEYWORD_ONLY", True),
                    ("terminal_backend", "KEYWORD_ONLY", True),
                    ("agent_backend", "KEYWORD_ONLY", True),
                    ("parent_id", "KEYWORD_ONLY", True),
                    ("base_branch", "KEYWORD_ONLY", True),
                    ("acceptance_criteria", "KEYWORD_ONLY", True),
                ),
                "Task",
                "operator",
                True,
                "Create a new task.",
            ),
            (
                "tasks.delete",
                "delete_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "tuple[bool, str]",
                "maintainer",
                True,
                "Delete a task.",
            ),
            (
                "tasks.get",
                "get_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Task | None",
                "viewer",
                False,
                "Get a single task by ID.",
            ),
            (
                "tasks.list",
                "list_tasks",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("project_id", "KEYWORD_ONLY", True),
                    ("status", "KEYWORD_ONLY", True),
                ),
                "list[Task]",
                "viewer",
                False,
                "List tasks with optional project/status filter.",
            ),
            (
                "tasks.logs",
                "get_task_logs",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("limit", "KEYWORD_ONLY", True),
                    ("offset", "KEYWORD_ONLY", True),
                ),
                "dict[str, Any]",
                "viewer",
                False,
                "Return execution logs for a task.",
            ),
            (
                "tasks.move",
                "move_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("status", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Task | None",
                "operator",
                True,
                "Move a task to a new status column.",
            ),
            (
                "tasks.scratchpad",
                "get_scratchpad",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                ),
                "str",
                "viewer",
                False,
                "Get a task's scratchpad content.",
            ),
            (
                "tasks.search",
                "search_tasks",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("query", "POSITIONAL_OR_KEYWORD", False),
                ),
                "Sequence[Task]",
                "viewer",
                False,
                "Search tasks by text query.",
            ),
            (
                "tasks.update",
                "update_task",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("fields", "VAR_KEYWORD", False),
                ),
                "Task | None",
                "operator",
                True,
                "Update task fields.",
            ),
            (
                "tasks.update_scratchpad",
                "update_scratchpad",
                (
                    ("self", "POSITIONAL_OR_KEYWORD", False),
                    ("task_id", "POSITIONAL_OR_KEYWORD", False),
                    ("content", "POSITIONAL_OR_KEYWORD", False),
                ),
                "None",
                "pair_worker",
                True,
                "Append to task scratchpad.",
            ),
        ]

    def test_excluded_methods_are_not_exposed(self) -> None:
        from kagan.core.api import KaganAPI

        excluded = {
            "submit_job",
            "cancel_job",
            "get_job",
            "wait_job",
            "get_job_events",
            "merge_task",
            "rebase_task",
            "create_session",
            "kill_session",
            "attach_session",
            "session_exists",
        }
        for name in excluded:
            attr = getattr(KaganAPI, name, None)
            assert attr is not None, f"Method {name} not found on KaganAPI"
            assert not hasattr(attr, EXPOSE_ATTR), f"Method {name} should NOT have @expose but does"
