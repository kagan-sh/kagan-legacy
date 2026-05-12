"""Shared fixtures for ``tests/e2e_chat/vscode``.

All tests in this directory are gated by ``KAGAN_VSCODE_E2E=1`` and will
be skipped in standard CI. Set that variable in the nightly job that has a
display server (or runs headless via the VS Code test-electron launcher).

The vscode-test subprocess is driven from
``packages/vscode/test/integration/chat-flows.test.ts`` which uses the
live ``kagan web --fake-agent`` server booted by the ``kagan_server``
fixture (inherited from the parent conftest).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.e2e_chat.helpers.server_runtime import ServerHandle

# ── Top-level gate ─────────────────────────────────────────────────────────

pytestmark = [
    pytest.mark.e2e_chat,
    pytest.mark.skipif(
        os.environ.get("KAGAN_VSCODE_E2E") != "1",
        reason="VSCode e2e tests require KAGAN_VSCODE_E2E=1",
    ),
]

# Path to the vscode package root (absolute, not relative).
_VSCODE_PKG = Path(__file__).parents[3] / "packages" / "vscode"


# ── vscode-test launcher ────────────────────────────────────────────────────


def build_vscode_test_suite() -> None:
    """Compile the extension and TS integration tests.

    ``compile`` builds the extension itself (src/ → dist/); ``build:test``
    compiles test/ → .vscode-test-build/. Both are required before
    ``vscode-test`` can run the integration suite.
    """
    for script in ("compile", "build:test"):
        result = subprocess.run(
            ["pnpm", "run", script],
            cwd=_VSCODE_PKG,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pnpm {script} failed (rc={result.returncode}):\n{result.stdout}\n{result.stderr}"
            )


def run_vscode_test(
    server: ServerHandle,
    *,
    test_filter: str | None = None,
    timeout: float = 120.0,
) -> dict[str, object]:
    """Run vscode-test and return parsed result dict.

    The test suite emits a JSON summary line on stdout:
    ``KAGAN_RESULT: {...}`` which Python reads and returns.
    Any other output is included in the result for diagnostics.

    Args:
        server: A live ``ServerHandle`` whose ``base_url`` is injected as
            ``KAGAN_TEST_SERVER_URL`` into the extension host environment.
        test_filter: Optional Mocha grep pattern to limit which tests run.
        timeout: Wall-clock timeout in seconds.

    Returns:
        dict with keys ``passed``, ``failed``, ``output``, ``lines``.
    """
    env = {
        **os.environ,
        "KAGAN_TEST_SERVER_URL": server.base_url,
    }
    if test_filter:
        env["KAGAN_TEST_FILTER"] = test_filter

    cmd = ["pnpm", "exec", "vscode-test"]
    if test_filter:
        cmd += ["--grep", test_filter]

    result = subprocess.run(
        cmd,
        cwd=_VSCODE_PKG,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    lines = combined.splitlines()

    # Parse summary from the last JSON line emitted by the Mocha reporter.
    passed = 0
    failed = 0
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("KAGAN_RESULT:"):
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                payload = json.loads(stripped[len("KAGAN_RESULT:") :].strip())
                passed = int(payload.get("passed", 0))
                failed = int(payload.get("failed", 0))
                break
        # Fallback: Mocha human-readable summary lines
        if "passing" in stripped and not passed:
            with contextlib.suppress(ValueError):
                passed = int(stripped.split()[0])
        if "failing" in stripped and not failed:
            with contextlib.suppress(ValueError):
                failed = int(stripped.split()[0])

    return {
        "returncode": result.returncode,
        "passed": passed,
        "failed": failed,
        "output": combined,
        "lines": lines,
    }


@pytest.fixture(scope="session")
def vscode_test_built() -> None:
    """Session-scoped fixture: compile TS tests once per session."""
    build_vscode_test_suite()


@pytest.fixture
def vscode_runner(
    kagan_server: ServerHandle,
    vscode_test_built: None,
) -> Iterator[_VscodeRunner]:
    """Provide a callable that runs the vscode-test suite against the live server."""
    yield _VscodeRunner(server=kagan_server)


class _VscodeRunner:
    def __init__(self, server: ServerHandle) -> None:
        self._server = server

    def run(self, test_filter: str | None = None, timeout: float = 120.0) -> dict[str, object]:
        return run_vscode_test(self._server, test_filter=test_filter, timeout=timeout)
