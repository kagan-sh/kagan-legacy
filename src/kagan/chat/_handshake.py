"""ACP handshake and connection initialization."""

import asyncio
from pathlib import Path
from typing import Any

import acp
from acp.schema import ClientCapabilities, Implementation, McpServerStdio
from loguru import logger

from kagan.chat.acp import _ACP_CLIENT_NAME, _ACP_CLIENT_TITLE, _ACP_CLIENT_VERSION
from kagan.core import acp_handshake_timeout_seconds, default_db_path


async def execute_handshake(
    conn: Any,
    agent_backend: str,
    session_id: str,
    project_id: str | None,
    cwd: Path,
) -> tuple[str, Exception | None]:
    """Execute ACP handshake and return session ID or error.

    Args:
        conn: ACP agent connection
        agent_backend: Name of the agent backend
        session_id: Session identifier for MCP
        project_id: Active project ID (may be None)
        cwd: Current working directory

    Returns:
        Tuple of (acp_session_id, error). If error is not None, acp_session_id is empty.
    """
    timeout_s = acp_handshake_timeout_seconds(agent_backend)
    client_caps = ClientCapabilities(terminal=False)

    try:
        await asyncio.wait_for(
            conn.initialize(
                protocol_version=acp.PROTOCOL_VERSION,
                client_capabilities=client_caps,
                client_info=Implementation(
                    name=_ACP_CLIENT_NAME,
                    title=_ACP_CLIENT_TITLE,
                    version=_ACP_CLIENT_VERSION,
                ),
            ),
            timeout=timeout_s,
        )
        logger.info("ACP initialize completed")
    except Exception as exc:
        return "", exc

    db_path = str(default_db_path())
    mcp_server = McpServerStdio(
        name="kagan",
        command="kagan",
        args=[
            "mcp",
            "--session-id",
            session_id,
            "--db",
            db_path,
            "--admin",
            *(["--project-id", project_id] if project_id else []),
        ],
        env=[],
    )

    try:
        sess = await asyncio.wait_for(
            conn.new_session(cwd=str(cwd), mcp_servers=[mcp_server]),
            timeout=timeout_s,
        )
        acp_session_id = sess.session_id
        logger.info("ACP session created session_id={}", acp_session_id)
        return acp_session_id, None
    except Exception as exc:
        return "", exc
