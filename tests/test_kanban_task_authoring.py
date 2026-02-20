"""Kanban board: task CRUD and field authoring.

Covers:
- Create AUTO and PAIR tasks with full fields
- Task fields: title, description, acceptance_criteria, priority, type, agent_backend, base_branch
- Read back task details via get
- List and filter tasks by project
- Delete task
- Scratchpad append/read operations
- parse_task_status normalization and AUTO/PAIR guardrails
- parse_task_priority, parse_task_type, parse_terminal_backend
- parse_acceptance_criteria, build_task_update_fields
- parse_timeout_seconds, parse_events_limit, parse_events_offset
- parse_wait_timeout_seconds, parse_wait_for_status_filter
- parse_queue_lane, parse_runtime_session_event, parse_proposal_status
- require_str, optional_str, str_list, str_object_dict, parse_json_dict_list
- Task @mention link extraction regex
"""

from __future__ import annotations

import pytest

from kagan.core.adapters.db.schema import Task
from kagan.core.commands._parsing import (
    build_task_update_fields,
    optional_str,
    parse_acceptance_criteria,
    parse_events_limit,
    parse_events_offset,
    parse_json_dict_list,
    parse_queue_lane,
    parse_task_priority,
    parse_task_status,
    parse_task_type,
    parse_terminal_backend,
    parse_timeout_seconds,
    parse_wait_for_status_filter,
    parse_wait_timeout_seconds,
    require_str,
    str_list,
    str_object_dict,
)
from kagan.core.domain.enums import PairTerminalBackend, TaskPriority, TaskStatus, TaskType


class TestTaskCreation:
    """Creating tasks with all supported fields."""

    @pytest.mark.parametrize("task_type", [TaskType.AUTO, TaskType.PAIR])
    async def test_create_task_with_all_fields(self, state_manager, task_type: TaskType) -> None:
        task = Task.create(
            title=f"Full-field {task_type.value} task",
            description="Detailed description of the work",
            priority=TaskPriority.HIGH,
            task_type=task_type,
            status=TaskStatus.BACKLOG,
            agent_backend="claude",
            acceptance_criteria=["AC-1: Must pass tests", "AC-2: Must update docs"],
            project_id=state_manager.default_project_id,
        )
        created = await state_manager.create(task)

        assert created.id is not None
        assert created.title == f"Full-field {task_type.value} task"
        assert created.description == "Detailed description of the work"
        assert created.priority == TaskPriority.HIGH
        assert created.task_type == task_type
        assert created.status == TaskStatus.BACKLOG
        assert created.agent_backend == "claude"
        assert created.acceptance_criteria == ["AC-1: Must pass tests", "AC-2: Must update docs"]


class TestTaskReadAndList:
    """Reading and listing tasks."""

    async def test_get_task_by_id(self, state_manager, task_factory) -> None:
        task = task_factory(title="Readable task")
        created = await state_manager.create(task)
        fetched = await state_manager.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "Readable task"

    async def test_list_tasks_returns_all(self, state_manager, task_factory) -> None:
        for i in range(3):
            await state_manager.create(task_factory(title=f"Task {i}"))
        tasks = await state_manager.get_all(project_id=state_manager.default_project_id)
        assert len(tasks) >= 3


class TestTaskUpdate:
    """Updating task fields."""

    async def test_update_title_and_priority(self, state_manager, task_factory) -> None:
        task = task_factory(title="Original")
        created = await state_manager.create(task)
        updated = await state_manager.update(created.id, title="Updated", priority=TaskPriority.LOW)
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.priority == TaskPriority.LOW

    async def test_update_status(self, state_manager, task_factory) -> None:
        task = task_factory(title="Moveable")
        created = await state_manager.create(task)
        updated = await state_manager.update(created.id, status=TaskStatus.IN_PROGRESS)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS


class TestTaskDeletion:
    """Deleting tasks."""

    async def test_delete_removes_task(self, state_manager, task_factory) -> None:
        task = task_factory(title="Deleteable")
        created = await state_manager.create(task)
        await state_manager.delete(created.id)
        fetched = await state_manager.get(created.id)
        assert fetched is None


class TestScratchpad:
    """Scratchpad write and read operations for incremental notes."""

    async def test_scratchpad_update_and_read(self, state_manager, task_factory) -> None:
        from kagan.core.adapters.db.repositories.auxiliary import ScratchRepository

        task = task_factory(title="Noted task")
        created = await state_manager.create(task)

        scratch = ScratchRepository(state_manager.session_factory)
        await scratch.update_scratchpad(created.id, "Note 1\nNote 2")
        content = await scratch.get_scratchpad(created.id)
        assert "Note 1" in content
        assert "Note 2" in content


class TestParseTaskStatus:
    """parse_task_status normalizes various string inputs and rejects AUTO/PAIR."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("BACKLOG", TaskStatus.BACKLOG),
            ("backlog", TaskStatus.BACKLOG),
            ("in_progress", TaskStatus.IN_PROGRESS),
            ("IN-PROGRESS", TaskStatus.IN_PROGRESS),
            ("InProgress", TaskStatus.IN_PROGRESS),
            ("REVIEW", TaskStatus.REVIEW),
            ("done", TaskStatus.DONE),
            ("  BACKLOG  ", TaskStatus.BACKLOG),
        ],
    )
    def test_normalizes_valid_statuses(self, raw: str, expected: TaskStatus) -> None:
        assert parse_task_status(raw) == expected

    def test_rejects_auto_with_helpful_message(self) -> None:
        with pytest.raises(ValueError, match="AUTO/PAIR are task_type values"):
            parse_task_status("AUTO")

    def test_rejects_pair_with_helpful_message(self) -> None:
        with pytest.raises(ValueError, match="AUTO/PAIR are task_type values"):
            parse_task_status("PAIR")

    def test_rejects_invalid_status_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid task status value"):
            parse_task_status("UNKNOWN")

    def test_passes_through_taskstatus_enum(self) -> None:
        assert parse_task_status(TaskStatus.DONE) is TaskStatus.DONE

    def test_rejects_non_string_non_enum(self) -> None:
        with pytest.raises(ValueError, match="Invalid task status value"):
            parse_task_status(42)


class TestTaskMentionExtraction:
    """_extract_task_mentions regex extracts 8-char alphanumeric @mention IDs."""

    def test_extracts_single_mention(self) -> None:
        from kagan.core.services.tasks import _extract_task_mentions

        result = _extract_task_mentions("Depends on @AbCd1234")
        assert result == {"AbCd1234"}

    def test_extracts_multiple_mentions(self) -> None:
        from kagan.core.services.tasks import _extract_task_mentions

        result = _extract_task_mentions("Refs @aaaa1111 and @bbbb2222")
        assert result == {"aaaa1111", "bbbb2222"}

    def test_empty_description_returns_empty(self) -> None:
        from kagan.core.services.tasks import _extract_task_mentions

        assert _extract_task_mentions("") == set()

    def test_no_mentions_returns_empty(self) -> None:
        from kagan.core.services.tasks import _extract_task_mentions

        assert _extract_task_mentions("No mentions here") == set()

    def test_ignores_short_at_references(self) -> None:
        from kagan.core.services.tasks import _extract_task_mentions

        # @abc is only 3 chars, should not match the 8-char pattern
        result = _extract_task_mentions("See @abc for details")
        assert "abc" not in result


class TestRequireStr:
    """require_str extracts mandatory string params."""

    def test_valid_string(self) -> None:
        assert require_str({"key": "value"}, "key") == "value"

    def test_missing_key_raises(self) -> None:
        with pytest.raises(ValueError, match="key must be a string"):
            require_str({}, "key")

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="key must be a string"):
            require_str({"key": 42}, "key")


class TestOptionalStr:
    """optional_str normalizes strings, returns None for empty/non-string."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("hello", "hello"),
            ("  spaced  ", "spaced"),
            ("", None),
            ("   ", None),
            (None, None),
            (42, None),
        ],
    )
    def test_normalization(self, input_val, expected) -> None:
        assert optional_str(input_val) == expected


class TestStrList:
    """str_list converts lists, strips empties."""

    def test_filters_and_strips(self) -> None:
        assert str_list(["a", " b ", "", "c"]) == ["a", "b", "c"]

    def test_non_list_returns_empty(self) -> None:
        assert str_list("not a list") == []

    def test_empty_list(self) -> None:
        assert str_list([]) == []


class TestStrObjectDict:
    """str_object_dict normalizes dict keys to strings."""

    def test_valid_dict(self) -> None:
        result = str_object_dict({"k": "v"})
        assert result == {"k": "v"}

    def test_empty_dict_returns_none(self) -> None:
        assert str_object_dict({}) is None

    def test_non_dict_returns_none(self) -> None:
        assert str_object_dict("string") is None


class TestParseTaskPriority:
    """parse_task_priority: enum, int, string aliases."""

    def test_enum_passthrough(self) -> None:
        assert parse_task_priority(TaskPriority.HIGH) is TaskPriority.HIGH

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, TaskPriority.LOW),
            (1, TaskPriority.MEDIUM),
            (2, TaskPriority.HIGH),
        ],
    )
    def test_int_values(self, value, expected) -> None:
        assert parse_task_priority(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("LOW", TaskPriority.LOW),
            ("low", TaskPriority.LOW),
            ("MED", TaskPriority.MEDIUM),
            ("MEDIUM", TaskPriority.MEDIUM),
            ("HIGH", TaskPriority.HIGH),
            ("0", TaskPriority.LOW),
            ("2", TaskPriority.HIGH),
        ],
    )
    def test_string_aliases(self, value, expected) -> None:
        assert parse_task_priority(value) == expected

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid task priority"):
            parse_task_priority("CRITICAL")

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid task priority"):
            parse_task_priority([1, 2])


class TestParseTaskType:
    """parse_task_type: enum, string normalization."""

    def test_enum_passthrough(self) -> None:
        assert parse_task_type(TaskType.AUTO) is TaskType.AUTO

    @pytest.mark.parametrize("value", ["AUTO", "auto", "  Auto  ", "PAIR", "pair"])
    def test_valid_strings(self, value) -> None:
        result = parse_task_type(value)
        assert isinstance(result, TaskType)

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid task type"):
            parse_task_type("MANUAL")

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid task type"):
            parse_task_type(42)


class TestParseTerminalBackend:
    """parse_terminal_backend: None, enum, string normalization."""

    def test_none_returns_none(self) -> None:
        assert parse_terminal_backend(None) is None

    def test_enum_passthrough(self) -> None:
        assert parse_terminal_backend(PairTerminalBackend.TMUX) is PairTerminalBackend.TMUX

    @pytest.mark.parametrize("value", ["tmux", "TMUX", "nvim", "vscode", "cursor"])
    def test_valid_strings(self, value) -> None:
        result = parse_terminal_backend(value)
        assert isinstance(result, PairTerminalBackend)

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid terminal backend"):
            parse_terminal_backend("emacs")

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid terminal backend"):
            parse_terminal_backend(42)


class TestParseAcceptanceCriteria:
    """parse_acceptance_criteria: None, string, list."""

    def test_none_returns_empty(self) -> None:
        assert parse_acceptance_criteria(None) == []

    def test_string_wrapped_in_list(self) -> None:
        assert parse_acceptance_criteria("Must pass tests") == ["Must pass tests"]

    def test_empty_string_returns_empty(self) -> None:
        assert parse_acceptance_criteria("") == []
        assert parse_acceptance_criteria("   ") == []

    def test_list_filters_empty(self) -> None:
        result = parse_acceptance_criteria(["AC-1", "", "AC-2", "  "])
        assert result == ["AC-1", "AC-2"]

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="acceptance_criteria must be"):
            parse_acceptance_criteria(42)


class TestBuildTaskUpdateFields:
    """build_task_update_fields delegates to individual parsers."""

    def test_empty_params(self) -> None:
        assert build_task_update_fields({}) == {}

    def test_title_passthrough(self) -> None:
        result = build_task_update_fields({"title": "New title"})
        assert result == {"title": "New title"}

    def test_status_parsed(self) -> None:
        result = build_task_update_fields({"status": "BACKLOG"})
        assert result["status"] == TaskStatus.BACKLOG

    def test_priority_parsed(self) -> None:
        result = build_task_update_fields({"priority": "HIGH"})
        assert result["priority"] == TaskPriority.HIGH

    def test_task_type_parsed(self) -> None:
        result = build_task_update_fields({"task_type": "AUTO"})
        assert result["task_type"] == TaskType.AUTO

    def test_multiple_fields(self) -> None:
        result = build_task_update_fields(
            {
                "title": "T",
                "status": "IN_PROGRESS",
                "priority": 2,
                "acceptance_criteria": ["AC-1"],
            }
        )
        assert result["title"] == "T"
        assert result["status"] == TaskStatus.IN_PROGRESS
        assert result["priority"] == TaskPriority.HIGH
        assert result["acceptance_criteria"] == ["AC-1"]


class TestParseTimeoutSeconds:
    """parse_timeout_seconds: None, valid, negative, bool, non-numeric."""

    def test_none_returns_none(self) -> None:
        assert parse_timeout_seconds(None) is None

    def test_valid_float(self) -> None:
        assert parse_timeout_seconds(30.5) == 30.5

    def test_valid_int(self) -> None:
        assert parse_timeout_seconds(60) == 60.0

    def test_negative_returns_error(self) -> None:
        result = parse_timeout_seconds(-1)
        assert isinstance(result, str)
        assert ">= 0" in result

    def test_bool_returns_error(self) -> None:
        result = parse_timeout_seconds(True)
        assert isinstance(result, str)

    def test_string_returns_error(self) -> None:
        result = parse_timeout_seconds("thirty")
        assert isinstance(result, str)


class TestParseEventsLimit:
    """parse_events_limit: None default, valid, out of range, bool."""

    def test_none_returns_default(self) -> None:
        assert parse_events_limit(None) == 50

    def test_valid_int(self) -> None:
        assert parse_events_limit(10) == 10

    def test_zero_returns_error(self) -> None:
        result = parse_events_limit(0)
        assert isinstance(result, str)

    def test_over_max_returns_error(self) -> None:
        result = parse_events_limit(101)
        assert isinstance(result, str)

    def test_bool_returns_error(self) -> None:
        result = parse_events_limit(True)
        assert isinstance(result, str)


class TestParseEventsOffset:
    """parse_events_offset: None default, valid, negative, bool."""

    def test_none_returns_zero(self) -> None:
        assert parse_events_offset(None) == 0

    def test_valid_int(self) -> None:
        assert parse_events_offset(5) == 5

    def test_negative_returns_error(self) -> None:
        result = parse_events_offset(-1)
        assert isinstance(result, str)

    def test_bool_returns_error(self) -> None:
        result = parse_events_offset(True)
        assert isinstance(result, str)


class TestParseWaitTimeoutSeconds:
    """parse_wait_timeout_seconds: default, valid, string, zero, exceeds max, bool."""

    def test_none_returns_default(self) -> None:
        result = parse_wait_timeout_seconds(None, default_timeout=30, max_timeout=300)
        assert result == 30.0

    def test_valid_number(self) -> None:
        result = parse_wait_timeout_seconds(60, default_timeout=30, max_timeout=300)
        assert result == 60.0

    def test_valid_string_number(self) -> None:
        result = parse_wait_timeout_seconds("45.5", default_timeout=30, max_timeout=300)
        assert result == 45.5

    def test_zero_returns_error(self) -> None:
        result = parse_wait_timeout_seconds(0, default_timeout=30, max_timeout=300)
        assert isinstance(result, str)
        assert "> 0" in result

    def test_exceeds_max_returns_error(self) -> None:
        result = parse_wait_timeout_seconds(999, default_timeout=30, max_timeout=300)
        assert isinstance(result, str)
        assert "300" in result

    def test_bool_returns_error(self) -> None:
        result = parse_wait_timeout_seconds(True, default_timeout=30, max_timeout=300)
        assert isinstance(result, str)

    def test_empty_string_returns_error(self) -> None:
        result = parse_wait_timeout_seconds("", default_timeout=30, max_timeout=300)
        assert isinstance(result, str)


class TestParseWaitForStatusFilter:
    """parse_wait_for_status_filter: None, list, comma string, JSON, invalid."""

    def test_none_returns_none(self) -> None:
        assert parse_wait_for_status_filter(None) is None

    def test_list_of_statuses(self) -> None:
        result = parse_wait_for_status_filter(["BACKLOG", "DONE"])
        assert result == {"BACKLOG", "DONE"}

    def test_comma_string(self) -> None:
        result = parse_wait_for_status_filter("BACKLOG,IN_PROGRESS")
        assert result == {"BACKLOG", "IN_PROGRESS"}

    def test_json_string(self) -> None:
        result = parse_wait_for_status_filter('["REVIEW", "DONE"]')
        assert result == {"REVIEW", "DONE"}

    def test_inprogress_alias(self) -> None:
        result = parse_wait_for_status_filter(["INPROGRESS"])
        assert result == {"IN_PROGRESS"}

    def test_invalid_status_returns_error(self) -> None:
        result = parse_wait_for_status_filter(["UNKNOWN"])
        assert isinstance(result, str)
        assert "Invalid status filter" in result

    def test_empty_string_returns_none(self) -> None:
        assert parse_wait_for_status_filter("") is None

    def test_non_string_non_list_returns_error(self) -> None:
        result = parse_wait_for_status_filter(42)
        assert isinstance(result, str)


class TestParseQueueLane:
    """parse_queue_lane: None default, valid lanes, invalid."""

    def test_none_defaults_to_implementation(self) -> None:
        assert parse_queue_lane(None) == "implementation"

    @pytest.mark.parametrize("lane", ["implementation", "review", "planner"])
    def test_valid_lanes(self, lane) -> None:
        assert parse_queue_lane(lane) == lane

    def test_case_insensitive(self) -> None:
        assert parse_queue_lane("REVIEW") == "review"

    def test_invalid_returns_error(self) -> None:
        result = parse_queue_lane("deploy")
        assert "must be one of" in result


class TestParseRuntimeSessionEvent:
    """parse_runtime_session_event: enum passthrough, valid strings, invalid."""

    def test_valid_strings(self) -> None:
        from kagan.core.commands._parsing import parse_runtime_session_event
        from kagan.core.services.runtime import RuntimeSessionEvent

        result = parse_runtime_session_event("project_selected")
        assert result == RuntimeSessionEvent.PROJECT_SELECTED

    def test_alias_normalization(self) -> None:
        from kagan.core.commands._parsing import parse_runtime_session_event
        from kagan.core.services.runtime import RuntimeSessionEvent

        result = parse_runtime_session_event("repo-selected")
        assert result == RuntimeSessionEvent.REPO_SELECTED

    def test_invalid_returns_none(self) -> None:
        from kagan.core.commands._parsing import parse_runtime_session_event

        assert parse_runtime_session_event("unknown") is None

    def test_non_string_returns_none(self) -> None:
        from kagan.core.commands._parsing import parse_runtime_session_event

        assert parse_runtime_session_event(42) is None


class TestParseProposalStatus:
    """parse_proposal_status: enum passthrough, valid strings, invalid."""

    def test_valid_string(self) -> None:
        from kagan.core.commands._parsing import parse_proposal_status
        from kagan.core.domain.enums import ProposalStatus

        result = parse_proposal_status("draft")
        assert result == ProposalStatus.DRAFT

    def test_enum_passthrough(self) -> None:
        from kagan.core.commands._parsing import parse_proposal_status
        from kagan.core.domain.enums import ProposalStatus

        result = parse_proposal_status(ProposalStatus.APPROVED)
        assert result is ProposalStatus.APPROVED

    def test_invalid_string_returns_none(self) -> None:
        from kagan.core.commands._parsing import parse_proposal_status

        assert parse_proposal_status("unknown") is None

    def test_non_string_returns_none(self) -> None:
        from kagan.core.commands._parsing import parse_proposal_status

        assert parse_proposal_status(42) is None


class TestParseJsonDictList:
    """parse_json_dict_list: valid list, non-list, non-dict items."""

    def test_valid_list_of_dicts(self) -> None:
        result = parse_json_dict_list([{"a": 1}, {"b": 2}], field_name="items")
        assert result == [{"a": 1}, {"b": 2}]

    def test_non_list_returns_error(self) -> None:
        result = parse_json_dict_list("not a list", field_name="items")
        assert isinstance(result, str)
        assert "items must be a list" in result

    def test_non_dict_item_returns_error(self) -> None:
        result = parse_json_dict_list([{"a": 1}, "not a dict"], field_name="items")
        assert isinstance(result, str)
        assert "items items must be objects" in result
