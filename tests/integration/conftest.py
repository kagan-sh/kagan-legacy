"""Shared fixtures for integration tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


# ---------------------------------------------------------------------------
# Mock LLM proxy
# ---------------------------------------------------------------------------


def _make_openai_response(content: str = "ok") -> dict:
    """Minimal OpenAI chat completions response."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _make_anthropic_response(content: str = "ok") -> dict:
    """Minimal Anthropic messages response."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": "claude-test",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


class _MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence access logs
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # consume body
        if "/v1/messages" in self.path:
            body = json.dumps(_make_anthropic_response()).encode()
        else:
            body = json.dumps(_make_openai_response()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="session")
def mock_llm_proxy() -> Generator[str, None, None]:
    """Start a mock OpenAI/Anthropic-compatible LLM proxy on a random port.

    Yields the base URL: http://127.0.0.1:<port>
    """
    server = HTTPServer(("127.0.0.1", 0), _MockLLMHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
