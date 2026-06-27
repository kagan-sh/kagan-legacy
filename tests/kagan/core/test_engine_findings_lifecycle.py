"""Finding lifecycle across re-runs (WS2 — DESIGN-SHARE-08, B11/B12/B17).

Auto-generated findings (rubric/security/ai-review/machine) are REPLACED by source
on every run, so a send-back re-run never multiplies them. A send-back is a re-run
DIRECTIVE carried on Task.sendback_note — never a Finding — so it never gates approve
as a phantom blocker and never pollutes the receipt's disputed-findings list.
"""

import os
from pathlib import Path

from kagan.core import Harness, git
from kagan.core.enums import TaskState

CLI = "claude"

# A builder that just edits one in-scope file. No validate phase (no reviewer config),
# so the only findings come from the gate: the rubric bullets + the "security skipped"
# advisory — exactly the auto-generated set the dogfood saw double on re-run (B11).
BUILDER = """#!/bin/sh
mkdir -p src
echo "edit $(date +%s%N)" >> src/new.py
"""


def _install(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


async def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    await git.init_repo(path, initial_branch="main", create_initial_commit=False)
    (path / "README.md").write_text("base\n", encoding="utf-8")
    (path / ".kagan").mkdir(exist_ok=True)
    (path / ".kagan" / "repo.yaml").write_text("checks:\n  lint: 'true'\n", encoding="utf-8")
    # A rubric with three bullets → three question findings per gate run.
    (path / ".kagan" / "review.md").write_text(
        "# Rubric\n- Errors are handled\n- No secrets added\n- Tests cover new behaviour\n",
        encoding="utf-8",
    )
    await git.commit_all(path, "base")
    return path


async def _drive(core: Harness, task_id: str) -> None:
    await core.start_task(task_id)
    await core.await_agent(task_id)


async def test_auto_findings_replaced_by_source_on_rerun_not_accumulated(tmp_path, monkeypatch):
    # B11: after a send-back re-run, rubric/security findings are REPLACED, not stacked.
    # The dogfood saw 6 rubric questions become 12 and 1 security advisory become 2 after
    # a single send-back; this asserts the counts are stable across the re-run.
    repo = await _repo(tmp_path / "repo")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, BUILDER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])

    await _drive(core, task.id)
    first = core.get_task(task.id)
    rubric_first = [f for f in first.findings if f.source == "rubric"]
    security_first = [f for f in first.findings if f.source == "security"]
    assert len(rubric_first) == 3  # the three rubric bullets
    assert len(security_first) == 1  # the "security scan skipped" advisory

    await core.send_back(task.id, "please run fmt and fix clippy")
    await core.await_agent(task.id)

    second = core.get_task(task.id)
    assert second.state is TaskState.REVIEW
    # Stable counts — replaced by source, NOT doubled.
    assert len([f for f in second.findings if f.source == "rubric"]) == 3
    assert len([f for f in second.findings if f.source == "security"]) == 1


async def test_send_back_is_a_directive_not_a_finding(tmp_path, monkeypatch):
    # B12/B17: the send-back note rides on Task.sendback_note (consumed by the re-run
    # prompt, then cleared) — it is NEVER a Finding. So it cannot gate approve as a
    # phantom blocker, render titleless in the findings list, or appear in the receipt's
    # disputed-findings section with a circular reason = its own text.
    repo = await _repo(tmp_path / "repo")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, BUILDER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await _drive(core, task.id)

    note = "please run fmt and fix clippy"
    await core.send_back(task.id, note)
    await core.await_agent(task.id)

    settled = core.get_task(task.id)
    # No finding carries the send-back — not as a source, not by message.
    assert not any(f.source == "sendback" for f in settled.findings)
    assert not any(f.message == note for f in settled.findings)
    # The directive was consumed by the re-run prompt and cleared.
    assert settled.sendback_note is None
    # No blocking finding is open purely because of the send-back: the only findings are
    # the rubric/security questions (non-blocking), so approve is not phantom-gated.
    assert not any(f.severity == "blocking" and f.verdict is None for f in settled.findings)
    # The receipt's disputed-findings section is empty — the send-back never masquerades
    # as a finding the human disagreed with.
    receipt = core.render_receipt(task.id)
    assert "_No findings disputed._" in receipt
    assert note not in receipt
