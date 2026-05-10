"""Hermetic ACP echo agent for stdio integration tests.

Vendored from ``references/acp/examples/echo_agent.py`` (anthropics/agent-protocol).
The agent speaks the real ACP wire protocol and only depends on the ``acp``
package we already pin. Tests spawn this script as a subprocess via
``spawn_filtered_agent_process`` to exercise the full handshake → prompt →
notification → teardown path with no provider binary on PATH.
"""

# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = [
#     "agent-client-protocol",
# ]
# ///
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
)
from acp.interfaces import Client
from acp.schema import (
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
)


class EchoAgent(Agent):
    _conn: Client

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, client_info, kwargs
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        del cwd, mcp_servers, kwargs
        return NewSessionResponse(session_id=uuid4().hex)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        del kwargs
        for block in prompt:
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            chunk = update_agent_message(text_block(text))
            chunk.field_meta = {"echo": True}
            chunk.content.field_meta = {"echo": True}

            await self._conn.session_update(
                session_id=session_id, update=chunk, source="echo_agent"
            )
        return PromptResponse(stop_reason="end_turn")


async def main() -> None:
    await run_agent(EchoAgent())


if __name__ == "__main__":
    asyncio.run(main())
