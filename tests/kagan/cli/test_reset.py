"""`kagan reset` confirmation safety (F8).

The destructive confirm must fail CLOSED on non-interactive stdin: an open pipe
that never delivers a line would hang the prompt forever, and a stray piped 'yes'
would silently authorize a wipe. --yes/--force is the scripted path.
"""

import pytest
from click.testing import CliRunner

from kagan.cli import reset as reset_mod
from kagan.cli.main import cli


class _FakeClient:
    def __init__(self) -> None:
        self.reset_called = False

    async def reset(self) -> None:
        self.reset_called = True

    def close(self) -> None:
        pass


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(reset_mod, "make_client", lambda: client)
    # The data-dir probe walks real dirs; stub it so the test stays hermetic.
    monkeypatch.setattr(reset_mod, "_get_data_dirs", lambda: [])
    monkeypatch.setattr(reset_mod, "_prune_worktrees", lambda: None)
    return client


def test_reset_refuses_on_non_tty_stdin_and_never_wipes(fake_client):
    # CliRunner stdin is not a TTY, so the confirm must refuse and NOT call reset().
    # Before F8 an open non-TTY pipe would hang here instead of failing closed.
    result = CliRunner().invoke(cli, ["reset"], input="yes\n")
    assert result.exit_code == 0, result.output
    assert fake_client.reset_called is False  # a piped 'yes' must NOT authorize a wipe
    assert "refusing to reset" in result.output.lower()


def test_reset_yes_flag_wipes_without_prompt(fake_client):
    # --yes skips the interactive prompt entirely, so the wipe proceeds even with a
    # non-TTY stdin (the documented scripted path).
    result = CliRunner().invoke(cli, ["reset", "--yes"])
    assert result.exit_code == 0, result.output
    assert fake_client.reset_called is True


def test_reset_force_flag_still_wipes(fake_client):
    # --force keeps its existing bypass behavior.
    result = CliRunner().invoke(cli, ["reset", "--force"])
    assert result.exit_code == 0, result.output
    assert fake_client.reset_called is True
