"""GateEngine universal checks (TUI-GATE-02/03).

The mirror runs build/types/tests; this engine adds the diff heuristics, the
mutation probe, and the rubric. Each test breaks one production branch and
asserts the matching Finding appears (or does not), so it fails when the
heuristic regresses.
"""

from pathlib import Path

import pytest

from kagan.core import git
from kagan.core.config import RepoConfig
from kagan.core.gate import GateEngine
from kagan.core.models import Task
from kagan.core.reports import detect_drift


@pytest.fixture
async def worktree(tmp_path: Path):
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    await git.commit_all(repo, "base")
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")
    return repo, wt


@pytest.mark.asyncio
async def test_out_of_scope_edit_is_blocking_finding(worktree):
    # TUI-GATE-02: an edit outside the declared scope is a blocking finding.
    repo, wt = worktree
    (wt / "stray.py").write_text("x = 1\n", encoding="utf-8")
    await git.commit_all(wt, "edit outside scope")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=["src/"])

    findings = await GateEngine(repo_root=repo).run(task)

    scope = [f for f in findings if f.location == "stray.py"]
    assert len(scope) == 1
    assert scope[0].severity == "blocking"
    assert "scope" in scope[0].message.lower()


@pytest.mark.asyncio
async def test_glob_scope_admits_nested_file_and_flags_sibling(worktree):
    # F2: scope is path globs (src/**). A nested in-scope file (src/forecast.rs) must
    # NOT be flagged, while a sibling outside every glob (top.py) must be. This fails
    # if _scope ever reverts to str.startswith, which reads "src/**" as a literal.
    repo, wt = worktree
    (wt / "src").mkdir()
    (wt / "src" / "forecast.rs").write_text("fn main() {}\n", encoding="utf-8")
    (wt / "top.py").write_text("x = 1\n", encoding="utf-8")
    await git.commit_all(wt, "nested + sibling edit")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=["src/**"])

    findings = await GateEngine(repo_root=repo).run(task)

    scope = {f.location for f in findings if "scope" in f.message.lower()}
    assert "src/forecast.rs" not in scope  # nested in-scope file admitted by the glob
    assert "top.py" in scope  # genuinely out-of-scope sibling still flagged


@pytest.mark.asyncio
async def test_bare_prefix_scope_agrees_between_gate_and_drift(worktree):
    # Phase 10 Track A: a bare-prefix scope (src/) must classify a file identically
    # in the gate's _scope check and in reports.detect_drift, because both now route
    # through the one canonical matcher (core/paths.matches_scope). Before the unify,
    # detect_drift used fnmatch only and read "src/" as a literal, so an in-scope
    # file (src/real.py) mis-flagged as drift while the gate admitted it. This fails
    # if the two paths drift apart again.
    repo, wt = worktree
    (wt / "src").mkdir()
    (wt / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")  # in scope
    (wt / "top.py").write_text("y = 1\n", encoding="utf-8")  # out of scope
    await git.commit_all(wt, "in-scope + out-of-scope edit")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=["src/"])

    gate = await GateEngine(repo_root=repo).run(task)
    gate_scope = {f.location for f in gate if "scope" in f.message.lower()}

    diff = "diff --git a/src/real.py b/src/real.py\n+x = 1\ndiff --git a/top.py b/top.py\n+y = 1\n"
    drift_scope = {f.location for f in detect_drift(task, diff) if "scope" in f.message.lower()}

    # Same verdict on both files in both surfaces: src/real.py admitted, top.py flagged.
    assert "src/real.py" not in gate_scope and "src/real.py" not in drift_scope
    assert "top.py" in gate_scope and "top.py" in drift_scope


@pytest.mark.asyncio
async def test_kagan_generated_files_are_not_scope_findings(worktree):
    # F3: kagan writes .mcp.json and .kagan/{ask,prompt,agent.log} into every worktree
    # (recipe MCP config, prompt, agent log). They are kagan's own run-artifacts, not
    # agent work, so they must not trip the scope check — exactly as the harvest path
    # strips them. This fails if _changed_files stops filtering paths.is_run_artifact.
    repo, wt = worktree
    (wt / ".mcp.json").write_text("{}\n", encoding="utf-8")
    (wt / ".kagan").mkdir(exist_ok=True)
    (wt / ".kagan" / "prompt.txt").write_text("prompt\n", encoding="utf-8")
    (wt / ".kagan" / "agent.log").write_text("log\n", encoding="utf-8")
    (wt / "src").mkdir()
    (wt / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")  # the genuine edit
    await git.commit_all(wt, "agent edit + kagan scaffolding")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=["src/**"])

    findings = await GateEngine(repo_root=repo).run(task)

    flagged = {f.location for f in findings}
    assert ".mcp.json" not in flagged
    assert ".kagan/prompt.txt" not in flagged
    assert ".kagan/agent.log" not in flagged
    # And the in-scope real edit raises no scope finding either.
    assert not [f for f in findings if "scope" in f.message.lower()]


@pytest.mark.asyncio
async def test_secret_file_is_blocking_finding(worktree):
    # TUI-GATE-02: a committed secret file is a blocking finding.
    repo, wt = worktree
    (wt / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    await git.commit_all(wt, "add secret")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[".env"])

    findings = await GateEngine(repo_root=repo).run(task)

    secret = [f for f in findings if ".env" in f.location and "secret" in f.message.lower()]
    assert len(secret) == 1
    assert secret[0].severity == "blocking"


@pytest.mark.asyncio
async def test_uncommitted_untracked_secret_is_blocking_finding(worktree):
    # P5: harvest untracked files too — an agent that drops but never commits a
    # .env must still trip the secrets check.
    repo, wt = worktree
    (wt / ".env").write_text("TOKEN=abc\n", encoding="utf-8")  # left uncommitted
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[".env"])

    findings = await GateEngine(repo_root=repo).run(task)

    secret = [f for f in findings if ".env" in f.location and "secret" in f.message.lower()]
    assert len(secret) == 1
    assert secret[0].severity == "blocking"


@pytest.mark.asyncio
async def test_pinned_shared_env_edit_is_blocking_finding(worktree):
    # TUI-GATE-02: touching a pinned shared-env path is a blocking finding.
    repo, wt = worktree
    (wt / "uv.lock").write_text("locked\n", encoding="utf-8")
    await git.commit_all(wt, "touch lockfile")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=["uv.lock"])
    config = RepoConfig(pinned=["uv.lock"])

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    env = [f for f in findings if f.location == "uv.lock" and "pinned" in f.message.lower()]
    assert len(env) == 1
    assert env[0].severity == "blocking"


@pytest.mark.asyncio
async def test_large_diff_is_a_question_not_blocking(worktree):
    # TUI-GATE-02: a non-minimal diff is a question, not a hard block.
    repo, wt = worktree
    for i in range(GateEngine.MAX_FILES + 1):
        (wt / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
    await git.commit_all(wt, "many files")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo).run(task)

    minimal = [
        f for f in findings if "minimal" in f.message.lower() or "files" in f.message.lower()
    ]
    assert minimal and minimal[0].severity == "question"


@pytest.mark.asyncio
async def test_rubric_lines_become_question_findings(worktree):
    # TUI-GATE-03: the repo rubric is surfaced as question findings, not hardcoded.
    repo, wt = worktree
    (repo / ".kagan").mkdir()
    (repo / ".kagan" / "review.md").write_text(
        "# Rubric\n- No print statements\n- Tests added for new code\n", encoding="utf-8"
    )
    config = RepoConfig(review_rubric=Path(".kagan/review.md"))
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    rubric = [f for f in findings if f.severity == "question" and "print" in f.message.lower()]
    assert len(rubric) == 1


@pytest.mark.asyncio
async def test_mutation_probe_passes_when_test_command_can_fail(worktree):
    # TUI-GATE-02: a real test command returns non-zero on the injected failing
    # test, so no mutation finding is raised.
    repo, wt = worktree
    config = RepoConfig(checks={"test": "python -m pytest -q"})
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    assert not [f for f in findings if "mutation" in f.message.lower()]


@pytest.mark.asyncio
async def test_mutation_probe_flags_tautological_test_command(worktree):
    # TUI-GATE-02: a pytest command that swallows its own failure (always exits 0) is
    # a tautology -> blocking mutation finding. The command names pytest so it reaches
    # the probe's inject/run path, then `|| true` masks the injected failure's rc.
    repo, wt = worktree
    config = RepoConfig(checks={"test": "python -m pytest -q || true"})
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    probe = [f for f in findings if "mutation" in f.message.lower()]
    assert len(probe) == 1
    assert probe[0].severity == "blocking"


@pytest.mark.asyncio
async def test_mutation_probe_skipped_on_non_python_test_command(worktree):
    # F4: the probe injects a pytest file, so a non-python runner (cargo/go/npm) would
    # never collect it and exit 0 would be a vacuous green check. Such a command must
    # yield exactly one advisory "skipped" finding and ZERO blocking — never a silent
    # false pass that claims the suite has teeth.
    repo, wt = worktree
    config = RepoConfig(checks={"test": "cargo test"})
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    probe = [f for f in findings if "mutation" in f.message.lower()]
    assert len(probe) == 1
    assert probe[0].severity == "question"
    assert "skipped" in probe[0].message.lower()
    assert not [f for f in findings if "mutation" in f.message.lower() and f.severity == "blocking"]


@pytest.mark.asyncio
async def test_security_finding_blocking_on_high_risk_advisory_otherwise(worktree):
    # Lever 3: a failing SAST command is a finding whose severity is ROUTED by the
    # task's risk — blocking on high-risk scope, advisory (question) elsewhere
    # (DESIGN L168). `false` stands in for a scanner that found issues. The test
    # would fail if the severity were fixed regardless of tier.
    repo, wt = worktree
    config = RepoConfig(security="false")

    high = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""], risk="high")
    findings = await GateEngine(repo_root=repo, config=config).run(high)
    sec = [f for f in findings if f.source == "security" and "issues" in f.message.lower()]
    assert len(sec) == 1
    assert sec[0].severity == "blocking"

    med = Task(id="t-2", title="T", worktree_path=wt, base_branch="main", scope=[""], risk="medium")
    findings = await GateEngine(repo_root=repo, config=config).run(med)
    sec = [f for f in findings if f.source == "security" and "issues" in f.message.lower()]
    assert len(sec) == 1
    assert sec[0].severity == "question"


@pytest.mark.asyncio
async def test_security_passes_emit_no_finding(worktree):
    # A clean scan (exit 0) raises nothing — the gate only reports real issues.
    repo, wt = worktree
    config = RepoConfig(security="true")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""], risk="high")

    findings = await GateEngine(repo_root=repo, config=config).run(task)

    assert not [f for f in findings if f.source == "security" and "issues" in f.message.lower()]


@pytest.mark.asyncio
async def test_security_skipped_is_visible_not_a_silent_pass(worktree):
    # Rule 12: with no security command declared the gate emits an explicit
    # "skipped" finding (advisory) — absence of a scanner must be visible in the
    # receipt, never reported as security-clean.
    repo, wt = worktree
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""], risk="high")

    findings = await GateEngine(repo_root=repo).run(task)

    skipped = [f for f in findings if f.source == "security" and "skipped" in f.message.lower()]
    assert len(skipped) == 1
    assert skipped[0].severity == "question"


@pytest.mark.asyncio
async def test_secrets_regex_spares_template_but_flags_real_key(worktree):
    # TUI-GATE-02: the secrets regex must tell a safe template (.env.example)
    # apart from a real key (key.pem), or it either nags or leaks.
    repo, wt = worktree
    (wt / ".env.example").write_text("TOKEN=changeme\n", encoding="utf-8")
    (wt / "key.pem").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    task = Task(id="t-1", title="T", worktree_path=wt, base_branch="main", scope=[""])

    findings = await GateEngine(repo_root=repo).run(task)

    assert not [
        f for f in findings if f.location == ".env.example" and "secret" in f.message.lower()
    ]
    key = [f for f in findings if f.location == "key.pem" and "secret" in f.message.lower()]
    assert len(key) == 1
