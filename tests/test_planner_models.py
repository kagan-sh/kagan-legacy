"""Planner model regression tests for canonical payload reuse and boundary clarity."""

from __future__ import annotations

from dataclasses import is_dataclass

import pytest

from kagan.core.agents.planner_models import (
    PlannerTaskDraft,
    PlanProposal,
    ProposedTask,
)
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType


class TestPlannerModelReuse:
    """Planner-specific payload models should reuse canonical domain DTOs."""

    def test_conflicting_task_type_alias_still_errors(self) -> None:
        with pytest.raises(ValueError, match="Conflicting task type values"):
            ProposedTask.model_validate(
                {
                    "title": "Conflicting type",
                    "type": "PAIR",
                    "task_type": "AUTO",
                }
            )


class TestPlannerProposalConversions:
    """Validated planner payloads convert to internal drafts and runtime tasks."""

    def test_to_task_drafts_uses_dataclass_internal_state(self) -> None:
        proposal = PlanProposal.model_validate(
            {
                "tasks": [
                    {
                        "title": "  Build coercion helpers  ",
                        "task_type": "auto",
                        "priority": "MED",
                        "acceptance_criteria": "  Keep behavior stable  ",
                    }
                ],
                "todos": [
                    {
                        "content": "  Normalize planner payloads  ",
                        "status": "FAILED",
                    }
                ],
            }
        )

        drafts = proposal.to_task_drafts()
        assert len(drafts) == 1
        draft = drafts[0]

        assert isinstance(draft, PlannerTaskDraft)
        assert is_dataclass(draft)
        assert draft.title == "Build coercion helpers"
        assert draft.task_type == TaskType.AUTO
        assert draft.priority == TaskPriority.MEDIUM
        assert draft.acceptance_criteria == ["Keep behavior stable"]

    def test_to_tasks_and_plan_entries_remain_compatible(self) -> None:
        proposal = PlanProposal.model_validate(
            {
                "tasks": [
                    {
                        "title": "Create plan task",
                        "type": "PAIR",
                        "priority": "high",
                    }
                ],
                "todos": [
                    {
                        "content": "Finish planning",
                        "status": "failed",
                    }
                ],
            }
        )

        tasks = proposal.to_tasks()
        entries = proposal.to_plan_entries()

        assert len(tasks) == 1
        assert tasks[0].status == TaskStatus.BACKLOG
        assert tasks[0].task_type == TaskType.PAIR
        assert tasks[0].priority == TaskPriority.HIGH

        assert len(entries) == 1
        assert entries[0].status == "completed"
