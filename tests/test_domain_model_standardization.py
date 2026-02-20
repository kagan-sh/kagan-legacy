"""Domain model standardization regression tests.

Ensures canonical Pydantic domain models are reused across SDK/MCP boundaries
and remain compatible with core serialization helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from kagan.core.commands._serialization import (
    execution_to_dict,
    project_to_dict,
    runtime_context_to_dict,
    runtime_view_to_dict,
    task_to_dict,
)
from kagan.core.domain import models as domain_models
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType
from kagan.mcp import _response_models
from kagan.sdk import _types as sdk_types


class TestCanonicalModelReuse:
    """SDK and MCP should reuse canonical core domain models directly."""

    def test_canonical_models_are_fully_built_at_import_time(self) -> None:
        model_names = (
            "PlanItem",
            "PlanTodo",
            "Project",
            "Repo",
            "TaskRuntimeState",
            "Task",
            "TaskSummary",
            "Execution",
            "ExecutionLogEntry",
            "RuntimeContext",
            "StartupDecision",
            "RuntimeView",
        )
        for model_name in model_names:
            model_cls = getattr(domain_models, model_name)
            assert model_cls.__pydantic_complete__ is True

    def test_sdk_reuses_core_domain_models(self) -> None:
        assert sdk_types.PlanItem is domain_models.PlanItem
        assert sdk_types.PlanTodo is domain_models.PlanTodo
        assert sdk_types.Project is domain_models.Project
        assert sdk_types.Repo is domain_models.Repo
        assert sdk_types.Task is domain_models.Task
        assert sdk_types.Execution is domain_models.Execution
        assert sdk_types.ExecutionLogEntry is domain_models.ExecutionLogEntry

    def test_mcp_reuses_core_runtime_summary_models(self) -> None:
        assert _response_models.TaskRuntimeState is domain_models.TaskRuntimeState
        assert _response_models.TaskSummary is domain_models.TaskSummary


class TestSerializerCompatibility:
    """Core serializers should emit payloads matching canonical models."""

    def test_task_to_dict_matches_canonical_model(self) -> None:
        now = datetime.now(UTC)
        task = SimpleNamespace(
            id="task-12345678",
            project_id="proj-1",
            parent_id=None,
            title="Task title",
            description="Task description",
            status=TaskStatus.BACKLOG,
            priority=TaskPriority.MEDIUM,
            task_type=TaskType.PAIR,
            terminal_backend=None,
            agent_backend=None,
            acceptance_criteria=["one", "two"],
            base_branch="main",
            created_at=now,
            updated_at=now,
        )

        payload = task_to_dict(task)
        model = domain_models.Task.model_validate(payload)

        assert model.id == "task-12345678"
        assert payload["runtime"]["is_running"] is False
        assert "short_id" not in payload

    def test_project_to_dict_matches_canonical_model(self) -> None:
        project = SimpleNamespace(
            id="proj-1",
            name="Project",
            description="Description",
            last_opened_at=None,
        )
        payload = project_to_dict(project)
        model = domain_models.Project.model_validate(payload)

        assert model.id == "proj-1"
        assert "last_opened_at" not in payload

    def test_execution_and_runtime_payloads_match_canonical_models(self) -> None:
        execution = SimpleNamespace(
            id="exec-1",
            session_id="sess-1",
            run_reason="manual",
            executor_action={"name": "run"},
            status="running",
            exit_code=None,
            dropped=False,
            started_at="2026-01-01T00:00:00+00:00",
            completed_at=None,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            error=None,
            metadata_={"attempt": 1},
        )
        execution_payload = execution_to_dict(execution)
        runtime_context_payload = runtime_context_to_dict(
            SimpleNamespace(project_id="proj-1", repo_id="repo-1")
        )
        runtime_view_payload = runtime_view_to_dict(
            task_id="task-1",
            view=SimpleNamespace(
                phase="running",
                execution_id="exec-1",
                run_count=2,
                running_agent=object(),
                review_agent=None,
            ),
            runtime_service=None,
        )

        execution_model = domain_models.Execution.model_validate(execution_payload)
        runtime_context_model = domain_models.RuntimeContext.model_validate(runtime_context_payload)
        runtime_view_model = domain_models.RuntimeView.model_validate(runtime_view_payload)

        assert execution_model.id == "exec-1"
        assert runtime_context_model.project_id == "proj-1"
        assert runtime_view_model.task_id == "task-1"


class TestCanonicalCoercion:
    """Canonical domain models should normalize task/planner payload scalars consistently."""

    def test_task_model_coerces_task_enums_from_common_wire_forms(self) -> None:
        model = domain_models.Task.model_validate(
            {
                "id": "task-1",
                "project_id": "proj-1",
                "title": "Normalize enums",
                "status": "in-progress",
                "priority": "med",
                "task_type": "auto",
            }
        )

        assert model.status == TaskStatus.IN_PROGRESS
        assert model.priority == TaskPriority.MEDIUM
        assert model.task_type == TaskType.AUTO

    def test_plan_item_normalizes_aliases_and_scalar_fields(self) -> None:
        item = domain_models.PlanItem.model_validate(
            {
                "title": "  Refactor parser  ",
                "task_type": "auto",
                "priority": "MED",
                "acceptance_criteria": "  Keep compatibility  ",
            }
        )

        assert item.title == "Refactor parser"
        assert item.type == "AUTO"
        assert item.priority == "medium"
        assert item.acceptance_criteria == ["Keep compatibility"]

    def test_plan_todo_normalizes_status_and_content(self) -> None:
        todo = domain_models.PlanTodo.model_validate(
            {
                "content": "  Validate command payloads  ",
                "status": "InProgress",
            }
        )

        assert todo.content == "Validate command payloads"
        assert todo.status == "in_progress"
