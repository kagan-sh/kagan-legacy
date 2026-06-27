"""Finding lifecycle across re-runs (WS2 — DESIGN-SHARE-08, B11/B12/B17).

Auto-generated findings (security/ai-review/machine) are REPLACED by source on
every run, so a send-back re-run never multiplies them. A send-back is a re-run
DIRECTIVE carried on Task.sendback_note — never a Finding — so it never gates approve
as a phantom blocker and never pollutes the receipt's disputed-findings list.
"""

import os
from pathlib import Path

from kagan.core import Harness, git
from kagan.core.enums import TaskState

CLI = "claude"

# A builder that just edits one in-scope file. No validate phase (no reviewer config),
# so the only finding comes from the gate: the "security skipped" advisory — an
# auto-generated finding the dogfood saw double on re-run (B11).
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
    await git.commit_all(path, "base")
    return path


async def _drive(core: Harness, task_id: str) -> None:
    await core.start_task(task_id)
    await core.await_agent(task_id)


async def test_auto_findings_replaced_by_source_on_rerun_not_accumulated(tmp_path, monkeypatch):
    # B11: after a send-back re-run, auto-generated findings are REPLACED by source, not
    # stacked. The dogfood saw the security advisory become 2 after a single send-back;
    # this asserts the count is stable across the re-run.
    repo = await _repo(tmp_path / "repo")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, BUILDER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])

    await _drive(core, task.id)
    first = core.get_task(task.id)
    assert len([f for f in first.findings if f.source == "security"]) == 1  # the skipped advisory

    await core.send_back(task.id, "please run fmt and fix clippy")
    await core.await_agent(task.id)

    second = core.get_task(task.id)
    assert second.state is TaskState.REVIEW
    # Stable count — replaced by source, NOT doubled.
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
    # No blocking finding is open purely because of the send-back: the only finding is
    # the security advisory (non-blocking), so approve is not phantom-gated.
    assert not any(f.severity == "blocking" and f.verdict is None for f in settled.findings)
    # The receipt's disputed-findings section is empty — the send-back never masquerades
    # as a finding the human disagreed with.
    receipt = core.render_receipt(task.id)
    assert "_No findings disputed._" in receipt
    assert note not in receipt
