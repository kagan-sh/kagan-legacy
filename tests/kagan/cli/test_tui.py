"""Entrypoint ledger scoping — the ledger lives under the repo root, not a global folder."""

import subprocess
from pathlib import Path

from kagan.cli.tui import _resolve_data_dir


def _init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)


def test_data_dir_is_repo_root_state_dir(tmp_path: Path, monkeypatch) -> None:
    # Ledger scope: inside a git repo the data dir is <toplevel>/.kagan/state, so two
    # different repos get independent ledgers instead of bleeding through a global dir.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)  # assert the no-override default
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    sub = repo / "src"
    sub.mkdir()
    monkeypatch.chdir(sub)

    assert _resolve_data_dir(None) == repo.resolve() / ".kagan" / "state"


def test_data_dir_falls_back_to_cwd_outside_a_repo(tmp_path: Path, monkeypatch) -> None:
    # Outside a repo there is no toplevel; fall back to cwd/.kagan/state, never the
    # global platformdirs folder that bleeds tasks across repos.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)  # assert the no-override default
    monkeypatch.chdir(tmp_path)
    assert _resolve_data_dir(None) == tmp_path.resolve() / ".kagan" / "state"


def test_explicit_data_dir_override_is_kept(tmp_path: Path) -> None:
    # The --data-dir override remains authoritative (tests/embedding rely on it).
    explicit = tmp_path / "custom"
    assert _resolve_data_dir(explicit) == explicit
