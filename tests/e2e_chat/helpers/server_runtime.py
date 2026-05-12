"""Boot ``kagan web --fake-agent`` on a free port for HTTP-mode tests.

Used by the ``kagan_server`` pytest fixture in ``conftest.py``. Tests
that drive ``KaganCore`` in-process should use the in-proc director
helpers instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class ServerHandle:
    base_url: str
    port: int
    process: subprocess.Popen[bytes]
    db_path: Path

    async def aclose(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self.process.wait), timeout=5.0)
            except TimeoutError:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)


async def _wait_ready(base_url: str, *, timeout: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        while asyncio.get_event_loop().time() < deadline:
            with contextlib.suppress(httpx.HTTPError):
                response = await client.get("/api/v1/health")
                if response.status_code < 500:
                    return
            await asyncio.sleep(0.2)
    raise RuntimeError(f"kagan web did not become ready at {base_url} within {timeout}s")


async def boot_kagan_web(workdir: Path, *, fake_agent_delay_ms: int = 100) -> ServerHandle:
    port = _free_port()
    db_path = workdir / "kagan.db"
    env = {
        **os.environ,
        "KAGAN_FAKE_AGENT": "1",
        "KAGAN_FAKE_AGENT_DELAY_MS": str(fake_agent_delay_ms),
        "KAGAN_DATA_DIR": str(workdir),
        "XDG_DATA_HOME": str(workdir),
    }
    cmd = [
        sys.executable,
        "-m",
        "kagan",
        "web",
        "--fake-agent",
        "--no-open",
        "--port",
        str(port),
        "--db",
        str(db_path),
    ]
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=workdir,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        await _wait_ready(base_url)
    except Exception:
        process.terminate()
        raise
    return ServerHandle(base_url=base_url, port=port, process=process, db_path=db_path)


__all__ = ["ServerHandle", "boot_kagan_web"]
