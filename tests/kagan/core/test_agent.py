import asyncio
import contextlib
import os
import signal
import subprocess

from kagan.core.agent import (
    _agent_env,
    _run_prompt,
    launch_intake,
    launch_manifest_draft,
    launch_run,
    terminate,
    wait_bounded,
)
from kagan.core.models import Finding, Task
from kagan.core.onboard import parse_manifest_report
from kagan.core.recipes import RECIPES, LaunchRecipe
from kagan.core.reports import read_ask

FAKE_AGENT = """#!/bin/sh
# Echo agent: append a report, try to write the repo (must fail under intake).
echo "writing" > wrote.txt 2>/dev/null || true
mkdir -p .kagan
echo '{"type":"intake_decisions","payload":{"decisions":[]}}' >> .kagan/ask
"""

SLEEPER = """#!/bin/sh
sleep 30
"""

# Reports via the KAGAN_ASK_PATH the harness hands it — proving the fallback channel
# is wired (F6). If the env var is unset the agent writes nothing and the test fails.
ASK_PATH_AGENT = """#!/bin/sh
[ -n "$KAGAN_ASK_PATH" ] && echo '{"type":"intake_decisions","payload":{"decisions":[]}}' >> "$KAGAN_ASK_PATH"
"""


# Simulates a real plan-mode CLI (claude --permission-mode=plan / codex -s read-only):
# if a read-only/plan sandbox flag is in argv it writes NOTHING (the CLI's own sandbox
# would reject every write, incl. the .kagan/ask report); otherwise it reports a real
# manifest via KAGAN_ASK_PATH. The recipe must therefore NOT pass such a flag, or the
# draft silently vanishes to the skeleton floor (R-002).
PLAN_AWARE_AGENT = """#!/bin/sh
for a in "$@"; do
  case "$a" in
    --permission-mode=plan|--read-only|-s|read-only|--sandbox=read-only)
      exit 0 ;;  # plan/read-only sandbox: report channel is severed, write nothing
  esac
done
[ -n "$KAGAN_ASK_PATH" ] && printf '%s\\n' \
  '{"type":"manifest","payload":{"base_branch":"main","checks":[{"name":"test","command":"pytest","provenance":"ci","source":"ci.yml"}]}}' \
  >> "$KAGAN_ASK_PATH"
"""


# Simulates opencode: it ignores cwd and operates on the dir given by --dir. Without a
# correct --dir it writes NOTHING to the sandbox (mutating the wrong tree). With it, it
# appends the report to that dir's .kagan/ask. Proves the workdir_flag recipe shape
# threads the sandbox path through _build_cmd, or the report lands in the wrong place.
WORKDIR_AGENT = """#!/bin/sh
dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$dir" ] && printf '%s\\n' \
  '{"type":"manifest","payload":{"base_branch":"main","checks":[{"name":"test","command":"pytest","provenance":"ci","source":"ci.yml"}]}}' \
  >> "$dir/.kagan/ask"
"""


def _install(bin_dir, name, body):
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


async def test_intake_reports_and_cannot_write_repo(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hello")
    task = Task(id="t-1", title="do thing", agent_cli="fakeagent")

    reports, ok = await launch_intake(task, repo)

    assert any(r.type == "intake_decisions" for r in reports)
    assert ok  # the fake agent exits 0
    # Real repo untouched: the agent ran in a throwaway read-only sandbox.
    assert not (repo / "wrote.txt").exists()


async def test_intake_hands_agent_the_ask_path_fallback(tmp_path, monkeypatch):
    # F6: the intake sandbox has NO .mcp.json, so the MCP report tools do not exist
    # there — the .kagan/ask JSONL fallback is the only working channel. The harness
    # MUST set KAGAN_ASK_PATH in the intake child env (as it does for the run), or a
    # real agent's intake reports silently vanish. This agent reports ONLY via that
    # path, so a present report proves the env var reached the child.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "askagent", ASK_PATH_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hello")

    reports, ok = await launch_intake(Task(id="t-1", title="x", agent_cli="askagent"), repo)

    assert ok
    assert any(r.type == "intake_decisions" for r in reports)  # reported via KAGAN_ASK_PATH


async def test_manifest_draft_delivered_when_recipe_has_no_plan_flag(tmp_path, monkeypatch):
    # R-002 structural gate (CLAUDE.md rule 8): a plan-mode CLI reports ONLY when no
    # read-only/plan sandbox flag is passed (the flag severs its .kagan/ask write). With
    # the recipe carrying no such flag, launch_manifest_draft must harvest a real manifest
    # — NOT degrade to the skeleton floor. FAILS under the old recipe, where _build_cmd
    # appended --permission-mode=plan / --read-only and the fake CLI wrote nothing.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "planagent", PLAN_AWARE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setitem(RECIPES, "planagent", LaunchRecipe(["planagent"], prompt_flag=None))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hello")

    reports = await launch_manifest_draft("planagent", repo)
    draft = parse_manifest_report(reports)

    assert draft is not None and draft.checks  # a real draft, not the skeleton floor
    assert draft.checks[0].name == "test"


async def test_plan_mode_flag_in_recipe_severs_the_report(tmp_path, monkeypatch):
    # The negative half of the gate: prove the fake CLI's plan-flag detection is real, so
    # the positive test above is meaningful. A recipe that DOES carry a plan flag makes
    # the same CLI report nothing — exactly the R-002 failure the fix removes.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "planagent", PLAN_AWARE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setitem(
        RECIPES,
        "planagent",
        LaunchRecipe(["planagent", "--permission-mode=plan"], prompt_flag=None),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hello")

    reports = await launch_manifest_draft("planagent", repo)

    assert parse_manifest_report(reports) is None  # severed channel → skeleton floor


async def test_workdir_flag_recipe_shape_delivers_the_report(tmp_path, monkeypatch):
    # R-002 follow-up: a CLI that ignores cwd (opencode) reports nothing unless the recipe
    # pins it with --dir <sandbox>. This verifies _build_cmd threads the sandbox path via
    # workdir_flag end-to-end — the report reaches the harvested draft. FAILS if --dir is
    # dropped from the recipe or not injected (opencode would mutate the wrong tree).
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "wdagent", WORKDIR_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setitem(
        RECIPES, "wdagent", LaunchRecipe(["wdagent"], prompt_flag=None, workdir_flag="--dir")
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hello")

    reports = await launch_manifest_draft("wdagent", repo)
    draft = parse_manifest_report(reports)

    assert draft is not None and draft.checks  # report landed in the sandbox's .kagan/ask
    assert draft.checks[0].name == "test"


async def test_intake_works_when_repo_already_has_kagan_dir(tmp_path, monkeypatch):
    # A real repo always ships .kagan/repo.yaml; the read-only sandbox pass must
    # re-open .kagan so the prompt write and the agent's report still succeed.
    # Fails if the read-only chmod locks .kagan (PermissionError writing the prompt).
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    repo = tmp_path / "repo"
    (repo / ".kagan").mkdir(parents=True)
    (repo / ".kagan" / "repo.yaml").write_text("{}\n")

    reports, _ok = await launch_intake(
        Task(id="t-1", title="do thing", agent_cli="fakeagent"), repo
    )

    assert any(r.type == "intake_decisions" for r in reports)


async def test_intake_sandbox_survives_dangling_symlink_and_skips_ignored(tmp_path, monkeypatch):
    # The live crash: copytree raised shutil.Error on a dangling symlink and dropped
    # the TUI to the shell. Sandbox setup over a git repo with a dangling symlink AND a
    # git-ignored junk dir must NOT raise, must still run intake, and must NOT copy the
    # ignored junk (the tracked-files-only copy is the crash fix AND the bloat fix).
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "tracked.txt").write_text("real\n")
    (repo / ".gitignore").write_text("junk/\n")
    (repo / "junk").mkdir()
    (repo / "junk" / "huge.bin").write_text("x" * 1000)  # ignored — must not be copied
    os.symlink(repo / "missing-target", repo / "rust-toolchain")  # dangling symlink
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt", ".gitignore"], check=True)

    copied: dict[str, bool] = {}
    real_walk = os.walk

    def _record_walk(top, *a, **k):
        # capture the sandbox tree on the first read-only chmod pass
        for root, dirs, files in real_walk(top, *a, **k):
            for f in files:
                copied[f] = True
            yield root, dirs, files

    monkeypatch.setattr("kagan.core.agent.os.walk", _record_walk)

    reports, _ok = await launch_intake(Task(id="t-1", title="x", agent_cli="fakeagent"), repo)

    assert any(r.type == "intake_decisions" for r in reports)  # did not crash, ran
    assert "tracked.txt" in copied  # tracked file made it into the sandbox
    assert "huge.bin" not in copied  # git-ignored junk was excluded


async def test_intake_reaps_its_agent_when_cancelled(tmp_path, monkeypatch):
    # Orphaned intake agents: the intake proc must be reaped when its pass ends or is
    # cancelled (TUI closing), not left running. Spawn a sleeper intake, cancel the
    # awaiting task, and assert the captured proc was terminated (no orphan).
    import asyncio

    bin_dir = tmp_path / "bin"
    _install(bin_dir, "sleeper", SLEEPER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("hi")

    captured = {}
    real_spawn = __import__("kagan.core.agent", fromlist=["_spawn"])._spawn

    async def _spy_spawn(*a, **k):
        proc = await real_spawn(*a, **k)
        captured["proc"] = proc
        return proc

    monkeypatch.setattr("kagan.core.agent._spawn", _spy_spawn)

    coro = launch_intake(Task(id="t-1", title="x", agent_cli="sleeper"), repo)
    fut = asyncio.ensure_future(coro)
    while "proc" not in captured:
        await asyncio.sleep(0.05)
    fut.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await fut

    proc = captured["proc"]
    await asyncio.wait_for(proc.wait(), 5.0)  # reaped within grace, not orphaned 30s
    # terminate sends SIGTERM to the process group; a reaped sleeper exits on the
    # signal (negative returncode), not via its own 0 exit (which means it ran free).
    assert proc.returncode == -signal.SIGTERM


def test_agent_env_blanks_git_credential_helper():
    # Fix 1 (defense-in-depth): the agent's git must have NO credential helper, so an
    # HTTPS push has no on-disk keychain/store cred source. _agent_env injects the
    # GIT_CONFIG_* blanking trio. Fails if the helper is left intact.
    env = _agent_env("claude", {"KAGAN_RUN": "1"})
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_0"] == ""
    assert env["KAGAN_RUN"] == "1"  # per-call extras still layer on


def test_agent_env_drops_ssh_agent_socket(monkeypatch):
    # Fix 1 (defense-in-depth): SSH_AUTH_SOCK is in the essential allowlist (kagan's own
    # ls-remote needs it), so it would otherwise be forwarded to the agent and let an ssh
    # push authenticate. _agent_env must drop it for the agent specifically. Fails if the
    # socket leaks into the agent env.
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/ssh-agent.sock")
    assert "SSH_AUTH_SOCK" not in _agent_env("claude", {})


async def test_run_spawns_in_worktree_and_logs_to_file(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    task = Task(id="t-1", title="x", agent_cli="fakeagent", worktree_path=worktree)

    proc = await launch_run(task)
    await proc.wait()  # P4: watch via wait(), not stdout EOF

    assert any(r.type == "intake_decisions" for r in read_ask(worktree))
    # stdout/stderr went to a log file, not a PIPE (P4).
    assert (worktree / ".kagan" / "agent.log").exists()


async def test_terminate_kills_process_group(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "sleeper", SLEEPER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    task = Task(id="t-1", title="x", agent_cli="sleeper", worktree_path=worktree)

    proc = await launch_run(task)
    await terminate(proc)
    assert proc.returncode == -signal.SIGTERM


async def test_wait_bounded_times_out_and_kills() -> None:
    # F1: a runaway process is stopped at the cap and reaped, so a hung agent can't
    # strand a task forever (and its pid dies, letting reconcile reap it).
    proc = await asyncio.create_subprocess_exec("sleep", "30", start_new_session=True)
    exited = await wait_bounded(proc, 0.3)
    assert exited is False
    assert proc.returncode is not None  # killed, not left running


async def test_wait_bounded_returns_true_on_clean_exit() -> None:
    proc = await asyncio.create_subprocess_exec("true", start_new_session=True)
    assert await wait_bounded(proc, 5.0) is True
    assert proc.returncode == 0


async def test_wait_bounded_zero_disables_the_cap() -> None:
    # 0 means "no cap" — wait unbounded (the documented escape hatch).
    proc = await asyncio.create_subprocess_exec("true", start_new_session=True)
    assert await wait_bounded(proc, 0) is True


def test_run_prompt_delivers_sendback_verdict_to_the_rerun_agent() -> None:
    # #4: send-back must reach the re-run agent. The prompt carries the reviewer's
    # note, the upheld findings (fix), and the overruled ones (leave as-is, w/ reason).
    task = Task(
        id="task-sb",
        title="t",
        scope=["src/**"],
        findings=[
            Finding(
                id="sb-0",
                severity="blocking",
                location="",
                message="rounding is wrong for negatives",
                verdict="disagree",
                reply="rounding is wrong for negatives",
                source="sendback",
            ),
            Finding(
                id="f-1",
                severity="blocking",
                location="src/calc.py:12",
                message="no overflow guard",
                verdict="agree",
                source="ai-review",
            ),
            Finding(
                id="f-2",
                severity="question",
                location="src/calc.py:40",
                message="rename foo",
                verdict="disagree",
                reply="intentional public name",
                source="ai-review",
            ),
        ],
    )
    prompt = _run_prompt(task)
    assert "sent this back" in prompt
    assert "rounding is wrong for negatives" in prompt  # the directive
    assert "Fix these" in prompt and "src/calc.py:12: no overflow guard" in prompt
    assert "Leave these as-is" in prompt and "intentional public name" in prompt


def test_run_prompt_has_no_sendback_section_on_a_fresh_run() -> None:
    task = Task(id="task-fresh", title="t", scope=["src/**"])
    assert "sent this back" not in _run_prompt(task)
