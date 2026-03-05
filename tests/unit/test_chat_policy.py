import pytest

from kagan.chat.prompt import (
    _ORCHESTRATOR_SYSTEM_PROMPT,
    _format_user_request_block,
    _runtime_guidance_for_request,
)

pytestmark = [pytest.mark.unit]


def test_runtime_guidance_for_status_request_prefers_run_summary() -> None:
    guidance = _runtime_guidance_for_request("whats latest across all tasks?")
    assert guidance is not None
    assert "run_summary" in guidance


def test_runtime_guidance_for_log_request_uses_bounded_logs() -> None:
    guidance = _runtime_guidance_for_request("show logs and traceback for task x")
    assert guidance is not None
    assert "bounded" in guidance


def test_runtime_guidance_for_generic_request_is_none() -> None:
    guidance = _runtime_guidance_for_request("create three tasks for weather app")
    assert guidance is None


def test_format_user_request_block_includes_guidance_for_status_queries() -> None:
    block = _format_user_request_block("what's latest?")
    assert block.startswith("User request:\n")
    assert "Runtime guidance:" in block


def test_orchestrator_prompt_requires_parallel_waves_and_acceptance_criteria_quality() -> None:
    assert "Execution Parallelism Policy" in _ORCHESTRATOR_SYSTEM_PROMPT
    assert "run them concurrently" in _ORCHESTRATOR_SYSTEM_PROMPT
    assert "If overlap is uncertain" in _ORCHESTRATOR_SYSTEM_PROMPT
    assert "Create tasks with empty acceptance criteria" in _ORCHESTRATOR_SYSTEM_PROMPT
    assert "2-6 verifiable outcomes" in _ORCHESTRATOR_SYSTEM_PROMPT
