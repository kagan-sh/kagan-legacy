"""Tests for list_project_learnings query and learnings injection."""

from pathlib import Path

import pytest

from kagan.core._prompts import resolve_task_prompt


@pytest.mark.unit
def test_learnings_injected_into_prompt() -> None:
    """[LEARNING] notes appear as PROJECT CONTEXT section in resolved prompt."""
    import types

    task = types.SimpleNamespace(
        title="Add feature",
        description="",
        acceptance_criteria=[],
    )
    learnings = ["Always run poe check before committing", "Use loguru for logging"]
    result = resolve_task_prompt(task, settings={}, learnings=learnings)

    assert "PROJECT CONTEXT (from prior tasks):" in result
    assert "- Always run poe check before committing" in result
    assert "- Use loguru for logging" in result


@pytest.mark.unit
def test_empty_learnings_no_section() -> None:
    """Empty learnings list produces no PROJECT CONTEXT section."""
    import types

    task = types.SimpleNamespace(title="Fix bug", description="", acceptance_criteria=[])
    result = resolve_task_prompt(task, settings={}, learnings=[])
    assert "PROJECT CONTEXT" not in result


@pytest.mark.unit
def test_none_learnings_no_section() -> None:
    """None learnings (default) produces no PROJECT CONTEXT section."""
    import types

    task = types.SimpleNamespace(title="Fix bug", description="", acceptance_criteria=[])
    result = resolve_task_prompt(task, settings={})
    assert "PROJECT CONTEXT" not in result


@pytest.mark.unit
def test_learnings_ordering_preserved() -> None:
    """Learnings appear in the order passed (newest-first from DB)."""
    import types

    task = types.SimpleNamespace(title="Task", description="", acceptance_criteria=[])
    learnings = ["First learning", "Second learning", "Third learning"]
    result = resolve_task_prompt(task, settings={}, learnings=learnings)

    first_pos = result.index("First learning")
    second_pos = result.index("Second learning")
    third_pos = result.index("Third learning")
    assert first_pos < second_pos < third_pos


@pytest.mark.unit
def test_learnings_section_after_base_prompt() -> None:
    """PROJECT CONTEXT section appears after the base task prompt."""
    import types

    task = types.SimpleNamespace(
        title="Implement feature",
        description="",
        acceptance_criteria=["Test passes"],
    )
    learnings = ["Use typed enums"]
    result = resolve_task_prompt(task, settings={}, learnings=learnings)

    task_pos = result.index("Task: Implement feature")
    context_pos = result.index("PROJECT CONTEXT (from prior tasks):")
    assert task_pos < context_pos


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_project_learnings_dedup_and_cap(tmp_path: Path) -> None:
    """list_project_learnings deduplicates and caps at 20."""
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session as DBSession

    from kagan.core.models import Project, Task, TaskNote
    from kagan.core._tasks import Tasks
    from kagan.core.enums import TaskStatus, WorkMode

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    # Create project + task
    project_id_val: str = ""
    task_id_val: str = ""
    with DBSession(engine) as s:
        project = Project(name="Test Project")
        s.add(project)
        s.commit()
        s.refresh(project)
        project_id_val = str(project.id)

        task = Task(
            title="Test Task",
            project_id=project_id_val,
            status=TaskStatus.BACKLOG,
            execution_mode=WorkMode.AUTO,
        )
        s.add(task)
        s.commit()
        s.refresh(task)
        task_id_val = str(task.id)

        # Add 25 learning notes (should return 20 unique)
        for i in range(25):
            note = TaskNote(task_id=task_id_val, content=f"[LEARNING] learning number {i}")
            s.add(note)
        # Add a duplicate
        s.add(TaskNote(task_id=task_id_val, content="[LEARNING] learning number 0"))
        # Add a non-learning note (should be excluded)
        s.add(TaskNote(task_id=task_id_val, content="regular note, not a learning"))
        s.commit()

    tasks_obj = Tasks(engine, {})
    result = await tasks_obj.list_project_learnings(project_id_val)

    # Capped at 20
    assert len(result) == 20
    # No [LEARNING] prefix in returned strings
    for item in result:
        assert not item.startswith("[LEARNING]")
    # Non-learning note excluded
    assert "regular note, not a learning" not in result


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_project_learnings_project_isolation(tmp_path: Path) -> None:
    """Learnings from other projects are NOT included."""
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session as DBSession

    from kagan.core.models import Project, Task, TaskNote
    from kagan.core._tasks import Tasks
    from kagan.core.enums import TaskStatus, WorkMode

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    proj_a_id: str = ""
    proj_b_id: str = ""
    task_a_id: str = ""
    task_b_id: str = ""
    with DBSession(engine) as s:
        proj_a = Project(name="Project A")
        proj_b = Project(name="Project B")
        s.add(proj_a)
        s.add(proj_b)
        s.commit()
        s.refresh(proj_a)
        s.refresh(proj_b)
        proj_a_id = str(proj_a.id)
        proj_b_id = str(proj_b.id)

        task_a = Task(
            title="Task A",
            project_id=proj_a_id,
            status=TaskStatus.BACKLOG,
            execution_mode=WorkMode.AUTO,
        )
        task_b = Task(
            title="Task B",
            project_id=proj_b_id,
            status=TaskStatus.BACKLOG,
            execution_mode=WorkMode.AUTO,
        )
        s.add(task_a)
        s.add(task_b)
        s.commit()
        s.refresh(task_a)
        s.refresh(task_b)
        task_a_id = str(task_a.id)
        task_b_id = str(task_b.id)

        s.add(TaskNote(task_id=task_a_id, content="[LEARNING] Only for project A"))
        s.add(TaskNote(task_id=task_b_id, content="[LEARNING] Only for project B"))
        s.commit()

    tasks_obj = Tasks(engine, {})

    learnings_a = await tasks_obj.list_project_learnings(proj_a_id)
    assert "Only for project A" in learnings_a
    assert "Only for project B" not in learnings_a

    learnings_b = await tasks_obj.list_project_learnings(proj_b_id)
    assert "Only for project B" in learnings_b
    assert "Only for project A" not in learnings_b
