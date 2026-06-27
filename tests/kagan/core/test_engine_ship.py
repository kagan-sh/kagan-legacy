from pathlib import Path

import pytest

from kagan.core import Harness
from kagan.core.enums import TaskState


@pytest.mark.accept
@pytest.mark.asyncio
async def test_core_approve_commands_receipt_and_mark_pushed(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    task = core.update_task(task.id, branch="kagan/" + task.id, risk="low")

    task = core.transition_task(task.id, TaskState.REVIEW)
    # approve_task now records the approver and re-checks the gate (lever 6). Low
    # risk needs no comprehension note and a single approver, so it flips to READY.
    task = core.approve_task(task.id, approver="alice <a@x.io>")
    assert task.state == TaskState.READY
    assert task.approvers == ["alice <a@x.io>"]

    assert core.get_push_command(task.id) == f"git push -u origin {task.branch}"
    assert "gh pr create" in core.get_pr_command(task.id)
    assert "Reviewed-before-push receipt" in core.render_receipt(task.id)

    # mark_task_pushed is async now (lever 7 PR-URL capture); gh absent / no PR
    # degrades remote_pr_url to None and the flip still proceeds.
    task = await core.mark_task_pushed(task.id)
    assert task.state == TaskState.PR_OPEN
    core.close()


def test_confirm_retro_stops_the_ship_view_re_offering_the_learning(tmp_path: Path):
    # B22: after a learning is appended, the ship view (which re-reads the ledger each
    # frame) must stop offering it — confirm_retro records retro_appended and
    # propose_retro then returns None, so the stale templated text is never re-shown.
    repo = tmp_path / "repo"
    repo.mkdir()
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("Add feature")
    core.add_decision(task.id, question="precedence?", severity="blocking")
    core.answer_decision(task.id, core.get_task(task.id).decisions[0].id, answer="proper")

    assert core.propose_retro(task.id) is not None  # a learning is on offer
    core.confirm_retro(task.id, "operator precedence is proper, not left-to-right")

    assert core.get_task(task.id).retro_appended is True
    assert core.propose_retro(task.id) is None  # no longer re-offered
    core.close()
