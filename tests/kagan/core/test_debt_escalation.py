"""Lever 9 wired through the harness: cumulative scope debt escalates a tier at
classification time, and generation is NEVER blocked.

WHY (Rule 9): the whole point of the lever is teeth-without-a-block. A rotting
scope must route into heavier review (a tier bump the gate/validator/approver all
read off task.risk), but classifying a task must never raise — an exception on the
intake hot path would stall task creation, which DESIGN lever 9 explicitly forbids
("never refuses generation, no self-serve override"). debt_threshold=None must
leave every task exactly where today's risk_tiers put it.
"""

from pathlib import Path

import pytest

from kagan.core import Harness
from kagan.core.models import Finding
from tests.helpers.gitrepo import make_repo

_REPO_YAML = """\
risk_tiers:
  low:
    - docs/**
debt_threshold: {threshold}
"""


@pytest.fixture
async def repo(tmp_path: Path) -> Path:
    return await make_repo(tmp_path / "repo")


def _write_config(repo: Path, threshold: str) -> None:
    (repo / ".kagan").mkdir(exist_ok=True)
    (repo / ".kagan" / "repo.yaml").write_text(_REPO_YAML.format(threshold=threshold))


def _seed_prior_tasks_touching(core: Harness, scope: str, *files: str) -> None:
    # Prior shipped work in the scope, recorded via finding locations (the
    # best-effort touched-file set the ledger actually keeps).
    for i, f in enumerate(files):
        task = core.create_task(f"prior-{i}")
        task.scope = [scope]
        task.findings = [Finding(id=f, severity="nit", location=f, message="m")]
        core.save_task(task)


async def test_rotting_scope_is_escalated_at_classification(repo: Path, tmp_path: Path):
    # docs/** is a LOW glob, but three prior tasks rewrote it -> over a threshold of 2
    # the scope is hot, so a new docs task bumps low -> medium and routes into the
    # heavier ceremony automatically.
    _write_config(repo, threshold="2")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    _seed_prior_tasks_touching(core, "docs/**", "docs/a.md", "docs/b.md", "docs/c.md")

    task = core.create_task("new docs task")
    task = core.configure_task(task.id, scope=["docs/**"])

    assert task.risk == "medium"  # would be "low" without the debt escalation


async def test_escalation_never_bumps_below_the_glob_tier(repo: Path, tmp_path: Path):
    # With debt below the threshold the scope keeps its glob-derived tier; debt can
    # only ever RAISE, so a quiet low scope stays low (never bumped down or sideways).
    _write_config(repo, threshold="5")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    _seed_prior_tasks_touching(core, "docs/**", "docs/a.md")  # 1 prior, under threshold

    task = core.create_task("quiet docs task")
    task = core.configure_task(task.id, scope=["docs/**"])

    assert task.risk == "low"


async def test_threshold_none_disables_escalation(repo: Path, tmp_path: Path):
    # debt_threshold unset -> the lever is off and the scope keeps its glob tier even
    # when the area is hot. This is the "additive by default / behaves like today".
    _write_config(repo, threshold="null")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    _seed_prior_tasks_touching(core, "docs/**", "docs/a.md", "docs/b.md", "docs/c.md")

    task = core.create_task("hot docs task")
    task = core.configure_task(task.id, scope=["docs/**"])

    assert task.risk == "low"  # unchanged from today's behaviour


async def test_classification_never_raises_so_generation_is_not_blocked(repo: Path, tmp_path: Path):
    # The load-bearing constraint: even with a configured threshold and a hot scope,
    # classifying returns a tier and never raises — debt is a routing nudge, never a
    # refusal. configure_task completing IS the proof generation is not gated.
    _write_config(repo, threshold="0")  # everything over budget -> always escalates
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    _seed_prior_tasks_touching(core, "docs/**", "docs/a.md")

    task = core.create_task("t")
    task = core.configure_task(task.id, scope=["docs/**"])  # must not raise

    assert task.risk in {"low", "medium", "high"}  # a tier, not an error
