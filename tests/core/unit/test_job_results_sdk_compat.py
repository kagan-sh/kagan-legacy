from __future__ import annotations

from types import SimpleNamespace

from kagan.sdk._types import JobResponse
from kagan.tui.ui.utils.job_results import job_message, job_result_payload


def test_job_result_payload_accepts_sdk_job_response_result_payload() -> None:
    response = JobResponse.model_validate(
        {
            "success": True,
            "job_id": "job-1",
            "task_id": "task-1",
            "action": "start_agent",
            "status": "succeeded",
            "message": "Agent running",
            "result": {
                "success": True,
                "message": "Agent started",
                "runtime": {"is_running": True},
            },
        }
    )

    payload = job_result_payload(response)

    assert payload == {
        "success": True,
        "message": "Agent started",
        "runtime": {"is_running": True},
    }
    assert job_message(response, "fallback") == "Agent started"


def test_job_message_falls_back_to_top_level_message_when_payload_has_no_message() -> None:
    response = JobResponse.model_validate(
        {
            "success": True,
            "job_id": "job-2",
            "task_id": "task-2",
            "action": "stop_agent",
            "status": "succeeded",
            "message": "Agent stop queued",
            "result": {"success": True},
        }
    )

    assert job_message(response, "fallback") == "Agent stop queued"


def test_job_result_helpers_handle_records_without_result_attribute() -> None:
    record = SimpleNamespace(message="Agent running")

    assert job_result_payload(record) is None
    assert job_message(record, "fallback") == "Agent running"
