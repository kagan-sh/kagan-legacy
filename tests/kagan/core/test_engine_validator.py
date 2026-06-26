"""Lever 2 — the adversarial validator stage (DESIGN section 4 lever 2 / section 8).

Drives a task through harvest with a fake agent and proves the resurrected
VALIDATING state does real work: the path is RUNNING -> VALIDATING -> REVIEW, a
validator-reported finding lands with source="ai-review" merged alongside the
gate findings, and the human is still required to adjudicate it (approve stays
locked until verdicts). A second test pins the validator to a DIFFERENT model
from the builder, read from repo.yaml.
"""

import os
from pathlib import Path

from kagan.core import Harness, git
from kagan.core.agent import _build_cmd
from kagan.core.enums import TaskState

# Phased fake agent: the builder phase (KAGAN_RUN) edits in scope; the validator
# phase (KAGAN_VALIDATE, run read-only in a sandbox copy of the worktree) reports
# one blocking ai-review finding with a concrete failure path via .kagan/ask.
PHASED_AGENT = """#!/bin/sh
if [ -n "$KAGAN_VALIDATE" ]; then
  mkdir -p .kagan
  printf '%s\\n' '{"type":"findings","payload":{"findings":[{"severity":"blocking","location":"src/new.py","message":"unbounded recursion: input of depth>1000 stack-overflows","confidence":8,"status":"VERIFIED"}]}}' >> .kagan/ask
else
  mkdir -p src
  echo "edit" >> src/new.py
fi
"""


def _install(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


async def _repo(path: Path, manifest: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    await git.init_repo(path, initial_branch="main", create_initial_commit=False)
    (path / "README.md").write_text("base\n", encoding="utf-8")
    (path / ".kagan").mkdir(exist_ok=True)
    (path / ".kagan" / "repo.yaml").write_text(manifest, encoding="utf-8")
    await git.commit_all(path, "base")
    return path


# Tasks run under a real, recipe-backed CLI; the fake agent script is installed under
# this name and builder/reviewer models live in repo.yaml under `agents.<CLI>`.
CLI = "claude"


def _agents(builder: str | None = None, reviewer: str | None = None) -> str:
    lines = ["agents:", f"  {CLI}:"]
    if builder:
        lines.append(f"    builder: {builder}")
    if reviewer:
        lines.append(f"    reviewer: {reviewer}")
    return "\n".join(lines) + "\n"


async def test_harvest_runs_validator_through_validating_into_review(tmp_path, monkeypatch):
    # Lever 2: a reviewer is configured, so harvest goes RUNNING -> VALIDATING ->
    # REVIEW (not the old direct RUNNING -> REVIEW), the validator's finding lands
    # source="ai-review" MERGED with the gate's machine findings, and approve stays
    # LOCKED until the human adjudicates it. This fails if the validator never runs,
    # if VALIDATING is skipped, or if ai-review findings auto-resolve.
    repo = await _repo(tmp_path / "repo", "checks:\n  lint: 'true'\n" + _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW

    # The transition log proves the path passed through VALIDATING, not a direct hop.
    transitions = [
        (e["from"], e["to"])
        for e in core._ledger.read_events(task.id)
        if e.get("type") == "transition"
    ]
    assert ("running", "validating") in transitions
    assert ("validating", "review") in transitions

    # The validator's finding landed source-stamped, merged with the gate's machine
    # findings (lint check ran), carrying its confidence/status.
    ai = [f for f in task.findings if f.source == "ai-review"]
    assert len(ai) == 1
    assert ai[0].severity == "blocking"
    assert ai[0].confidence == 8
    assert ai[0].status == "VERIFIED"
    assert any(c.name == "lint" for c in task.checks)  # gate findings present too
    assert any(f.source == "machine" for f in task.findings) or any(
        f.source == "rubric" for f in task.findings
    )

    # The human still adjudicates the ai-review finding — it does NOT auto-resolve.
    # Comprehension recorded and EVERY other blocking finding cleared, approve stays
    # locked while the ai-review finding alone is still open; it unlocks only once the
    # human adjudicates it too (the validator gets no special pass).
    note = "Adds a recursive parser; could break on pathologically deep input."
    core.record_comprehension(task.id, "postcondition", note)
    core.record_comprehension(task.id, "what_breaks", note)
    others = [f for f in task.findings if f.severity == "blocking" and f.id != ai[0].id]
    for f in others:
        core.set_verdict(task.id, f.id, verdict="disagree", reply="kagan-generated, ignore")
    assert core.can_approve(task.id) is False  # the ai-review blocking finding holds
    core.set_verdict(task.id, ai[0].id, verdict="agree")
    assert core.can_approve(task.id) is True  # only after the human adjudicates it too


async def test_validator_uses_reviewer_model_not_builder_model(tmp_path, monkeypatch):
    # Lever 2: the validator must run with the repo.yaml `reviewer:` model, which is a
    # DIFFERENT model from the builder (single-agent self-review is the thing this
    # avoids). Capture the model handed to launch_validate and assert it is the
    # reviewer, not the builder. Fails if the harness picks the builder or auto-picks.
    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    captured: dict[str, str] = {}

    async def _spy_validate(task, *, model, timeout=None):
        captured["model"] = model
        return [], True

    monkeypatch.setattr("kagan.core.harness.launch_validate", _spy_validate)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    models = core._gate_config().agents.for_cli(CLI)
    assert captured["model"] == "opus"
    assert captured["model"] == models.reviewer
    assert captured["model"] != models.builder  # reviewer differs from builder


async def test_builder_runs_on_builder_model(tmp_path, monkeypatch):
    # The "different models" guarantee is two-sided: the BUILDER must run on repo.yaml
    # `builder:`, not the CLI default. Capture the model handed to launch_run and assert
    # it is the builder. Fails if launch_run ignores builder: (single-model self-review).
    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    captured: dict[str, str | None] = {}

    async def _spy_run(task, *, model=None):
        captured["model"] = model
        raise RuntimeError("stop after launch")  # we only need the model arg

    monkeypatch.setattr("kagan.core.harness.launch_run", _spy_run)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    try:
        await core.start_task(task.id)
    except RuntimeError:
        pass
    models = core._gate_config().agents.for_cli(CLI)
    assert captured["model"] == "sonnet"
    assert captured["model"] == models.builder
    assert captured["model"] != models.reviewer  # builder differs from reviewer


async def test_validator_runs_when_reviewer_equals_builder(tmp_path, monkeypatch):
    # Fix 6: reviewer == builder is a valid one-vendor setup (the anti-bias guarantee
    # is the fresh SEPARATE spawn, not vendor identity). The validator stage must STILL
    # run — nothing refuses on model equality. Fails if equality disables the stage.
    repo = await _repo(tmp_path / "repo", _agents("opus", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    captured: dict[str, str] = {}

    async def _spy_validate(task, *, model, timeout=None):
        captured["model"] = model
        return [], True

    monkeypatch.setattr("kagan.core.harness.launch_validate", _spy_validate)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    models = core._gate_config().agents.for_cli(CLI)
    assert captured["model"] == "opus"  # the validator ran, on the reviewer model
    assert models.reviewer == models.builder  # even though it equals the builder
    transitions = [
        (e["from"], e["to"])
        for e in core._ledger.read_events(task.id)
        if e.get("type") == "transition"
    ]
    assert ("running", "validating") in transitions  # the stage was not skipped


async def test_validator_failure_degrades_to_unaided_review(tmp_path, monkeypatch):
    # F2: the validator is an enhancement, not the floor. If launch_validate crashes,
    # the task must NOT strand in VALIDATING — it reaches REVIEW with a visible
    # (non-blocking) finding, validator_outcome=="failed", and the receipt banner
    # admits the gap honestly (no false "validated" provenance — the trust spiral).
    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    async def _boom(task, *, model, timeout=None):
        raise RuntimeError("validator process exploded")

    monkeypatch.setattr("kagan.core.harness.launch_validate", _boom)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW  # not stranded in VALIDATING
    assert task.validator_outcome == "failed"
    degraded = [f for f in task.findings if "Validator did not complete" in f.message]
    assert len(degraded) == 1
    assert degraded[0].severity != "blocking"  # surfaces, does not lock approve
    assert "validator unavailable" in core.render_receipt(task.id)


async def test_validator_timeout_degrades_to_unaided_review(tmp_path, monkeypatch):
    # F2: a TIMEOUT (or unclean exit) returns (reports, ok=False) WITHOUT raising — it
    # must NOT read as a clean "ran". Otherwise a hung validator (the prime F1 failure
    # mode) would falsely show as validated. Pins the ok=False degrade path distinctly
    # from the crash (raise) path above.
    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    async def _timed_out(task, *, model, timeout=None):
        return [], False  # exited unclean / hit the wall-clock cap, did not raise

    monkeypatch.setattr("kagan.core.harness.launch_validate", _timed_out)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert task.validator_outcome == "failed"  # NOT "ran"
    assert "validator unavailable" in core.render_receipt(task.id)


async def test_model_under_agents_section_reaches_the_validator_verbatim(tmp_path, monkeypatch):
    # The new model contract: a reviewer id written under `agents.<cli>` is passed
    # VERBATIM to the validator — kagan does no translation and no pre-spawn vendor
    # check (a cross-vendor mismatch is unrepresentable, since the model lives under its
    # CLI's own key). A model the CLI can't run would surface as an honest F2 degrade,
    # never a silent wrong-vendor run.
    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opencode/claude-opus-4-8"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    captured: dict[str, str] = {}

    async def _spy_validate(task, *, model, timeout=None):
        captured["model"] = model
        return [], True

    monkeypatch.setattr("kagan.core.harness.launch_validate", _spy_validate)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    core.update_task(task.id, risk="medium")
    await core.start_task(task.id)
    await core.await_agent(task.id)

    assert captured["model"] == "opencode/claude-opus-4-8"  # verbatim, no resolution


async def test_validator_stage_skipped_when_no_reviewer_configured(tmp_path, monkeypatch):
    # Degrade gracefully: with no reviewer in repo.yaml the validator stage is a
    # no-op and the task still reaches REVIEW (RUNNING -> REVIEW), so existing repos
    # behave as before. Fails if a missing reviewer raises or strands the task.
    repo = await _repo(tmp_path / "repo", "checks:\n  lint: 'true'\n")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert not any(f.source == "ai-review" for f in task.findings)
    transitions = [
        (e["from"], e["to"])
        for e in core._ledger.read_events(task.id)
        if e.get("type") == "transition"
    ]
    assert ("running", "validating") not in transitions


async def test_low_risk_scope_skips_the_validator_even_with_reviewer_configured(
    tmp_path, monkeypatch
):
    # Lever 4 x lever 2: low risk is machine checks only (DESIGN L175). With a
    # reviewer configured AND a low-tier scope, harvest must STILL skip the
    # validator — proving the SKIP is the risk guard, not the missing-reviewer one.
    # Fails if low risk runs the validator (it would transition through VALIDATING).
    repo = await _repo(
        tmp_path / "repo",
        _agents("sonnet", "opus") + "risk_tiers:\n  low:\n    - 'src/**'\n",
    )
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("tweak")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    assert core.get_task(task.id).risk == "low"  # classified at configure time

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert not any(f.source == "ai-review" for f in task.findings)
    transitions = [
        (e["from"], e["to"])
        for e in core._ledger.read_events(task.id)
        if e.get("type") == "transition"
    ]
    assert ("running", "validating") not in transitions


async def test_medium_risk_scope_runs_the_validator(tmp_path, monkeypatch):
    # The counterpart: a medium-tier scope (high glob present, scope not under it)
    # DOES run the validator, so the skip is genuinely tier-conditional, not
    # always-off. Goes RUNNING -> VALIDATING -> REVIEW with an ai-review finding.
    repo = await _repo(
        tmp_path / "repo",
        _agents("sonnet", "opus") + "risk_tiers:\n  high:\n    - 'src/auth/**'\n",
    )
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    assert core.get_task(task.id).risk == "medium"

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert any(f.source == "ai-review" for f in task.findings)
    transitions = [
        (e["from"], e["to"])
        for e in core._ledger.read_events(task.id)
        if e.get("type") == "transition"
    ]
    assert ("running", "validating") in transitions


# A builder that reports a LOW-confidence ai-review finding via .kagan/ask during
# the run (no validate phase needed), so run_gate's downgrade pass has something to
# act on even when the validator stage itself is skipped.
LOW_CONF_REPORTER = """#!/bin/sh
mkdir -p src .kagan
echo "edit" >> src/new.py
printf '%s\\n' '{"type":"findings","payload":{"findings":[{"severity":"blocking","location":"src/new.py","message":"maybe off-by-one","confidence":3}]}}' >> .kagan/ask
"""


async def test_low_confidence_ai_finding_downgraded_to_advisory_on_low_risk(tmp_path, monkeypatch):
    # DESIGN 3.8 wired through run_gate: on a LOW-risk task a confidence-3 ai-review
    # finding is below the bar, so the gate downgrades it to advisory ("question").
    # It is KEPT (still in findings, still adjudicable) but no longer locks approve.
    repo = await _repo(tmp_path / "repo", "risk_tiers:\n  low:\n    - 'src/**'\n")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, LOW_CONF_REPORTER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("tweak")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    ai = [f for f in task.findings if f.source == "ai-review"]
    assert len(ai) == 1  # kept, not dropped
    assert ai[0].severity == "question"  # downgraded


async def test_low_confidence_ai_finding_stays_blocking_on_high_risk(tmp_path, monkeypatch):
    # The same confidence-3 finding stays BLOCKING when the scope is high-risk
    # (high surfaces tentative findings). The business rule flips with the tier —
    # this is the assertion that fails if the threshold direction is wrong (Rule 9).
    repo = await _repo(tmp_path / "repo", "risk_tiers:\n  high:\n    - 'src/**'\n")
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, LOW_CONF_REPORTER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("auth change")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    assert core.get_task(task.id).risk == "high"
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    ai = [f for f in task.findings if f.source == "ai-review"]
    assert len(ai) == 1
    assert ai[0].severity == "blocking"


# Validator phase reports a finding AND two diff-specific comprehension prompts
# (medium tier floor is 2), so the gate's prompt set becomes the generated one.
GEN_PROMPTS_AGENT = """#!/bin/sh
if [ -n "$KAGAN_VALIDATE" ]; then
  mkdir -p .kagan
  printf '%s\\n' '{"type":"findings","payload":{"findings":[{"severity":"blocking","location":"src/new.py","message":"unbounded recursion: input of depth>1000 stack-overflows","confidence":8,"status":"VERIFIED"}]}}' >> .kagan/ask
  printf '%s\\n' '{"type":"comprehension_prompts","payload":{"prompts":[{"key":"recursion_bound","question":"What bounds the new recursive descent on deep input?"},{"key":"empty_input","question":"How does src/new.py behave on empty input?"}]}}' >> .kagan/ask
else
  mkdir -p src
  echo "edit" >> src/new.py
fi
"""


async def test_generated_prompts_surface_through_review_into_receipt(tmp_path, monkeypatch):
    # Lever 1+2 end-to-end: the validator GENERATES diff-specific comprehension
    # prompts; they replace the static tier set on the gate, gate approval on the
    # human's own-words answers, and the answered GENERATED questions appear in the
    # receipt. This fails if generation is not wired, if the static set still gates,
    # or if the receipt renders the static questions instead of the generated ones.
    from kagan.core.comprehension import prompts_for_risk, required_keys_for_task

    repo = await _repo(tmp_path / "repo", "checks:\n  lint: 'true'\n" + _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, GEN_PROMPTS_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert task.validator_outcome == "ran"

    # The gate now keys off the GENERATED prompts, not the static medium tier set.
    static_keys = {k for k, _ in prompts_for_risk(task.risk)}
    keys = required_keys_for_task(task)
    assert keys == ["recursion_bound", "empty_input"]
    assert not static_keys.intersection(keys)

    # Adjudicate the validator finding and answer ONLY the static keys: approve must
    # stay locked, proving the generated keys (not the static ones) are what gate.
    ai = [f for f in task.findings if f.source == "ai-review"]
    assert len(ai) == 1
    core.set_verdict(task.id, ai[0].id, verdict="agree")
    for k in static_keys:
        core.record_comprehension(task.id, k, "a generic note that is plenty long enough")
    assert core.can_approve(task.id) is False

    # Answering the generated keys in the author's own words unlocks approve.
    core.record_comprehension(
        task.id, "recursion_bound", "A depth counter caps recursion at 1000 before it overflows."
    )
    core.record_comprehension(
        task.id, "empty_input", "On empty input the parser returns the zero value, no crash."
    )
    assert core.can_approve(task.id) is True

    # The receipt carries the GENERATED questions with their answers, not the static set.
    receipt = core.render_receipt(task.id)
    assert "What bounds the new recursive descent on deep input?" in receipt
    assert "A depth counter caps recursion at 1000" in receipt
    assert "What does this change do, end to end?" not in receipt  # the static medium prompt


async def test_validator_failure_falls_back_to_static_prompts_with_honest_provenance(
    tmp_path, monkeypatch
):
    # Rule-8 floor: a degraded validator can never shrink the gate. When the validator
    # crashes it generates NO prompts, so the gate falls back to the static medium tier
    # set, and the receipt admits "validator unavailable" rather than faking provenance.
    from kagan.core.comprehension import prompts_for_risk, required_keys_for_task

    repo = await _repo(tmp_path / "repo", _agents("sonnet", "opus"))
    bin_dir = tmp_path / "bin"
    _install(bin_dir, CLI, GEN_PROMPTS_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    async def _boom(task, *, model, timeout=None):
        raise RuntimeError("validator process exploded")

    monkeypatch.setattr("kagan.core.harness.launch_validate", _boom)

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli=CLI, scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert task.validator_outcome == "failed"
    assert not task.comprehension_prompts  # nothing generated — the validator crashed

    # The gate falls back to the full static medium tier set (the floor holds).
    static_keys = [k for k, _ in prompts_for_risk(task.risk)]
    assert required_keys_for_task(task) == static_keys
    assert static_keys == ["postcondition", "what_breaks"]

    # The receipt's ceremony banner is honest about the missing validator.
    assert "validator unavailable" in core.render_receipt(task.id)


def test_build_cmd_appends_model_flag_only_when_model_supplied(tmp_path):
    # The model override is wired through _build_cmd: a recipe with a model_flag gets
    # the flag + name appended when a model is supplied, and nothing when it is None.
    prompt = tmp_path / "p.txt"
    prompt.write_text("x")
    with_model = _build_cmd("claude", prompt, cwd=tmp_path, model="claude-opus")
    assert with_model[with_model.index("--model") + 1] == "claude-opus"
    assert "--model" not in _build_cmd("claude", prompt, cwd=tmp_path, model=None)
