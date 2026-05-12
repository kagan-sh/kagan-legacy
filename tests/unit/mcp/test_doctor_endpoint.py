"""Contract tests for GET /api/doctor.

Verifies that the response shape matches DoctorReportResponse — the source of truth
for the TypeScript types consumed by web and VS Code Wave 2.
"""

from __future__ import annotations

from typing import Any

import pytest

import kagan.server._helpers as server_helpers
from kagan.cli.doctor import DoctorCheck
from kagan.server.responses import DoctorCheckResponse, DoctorReportResponse
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_doctor_short_circuits_when_kagan_e2e_temp_dir_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Isolated Playwright webServer sets KAGAN_E2E_TEMP_DIR — doctor must not block UI."""

    def _boom() -> list[DoctorCheck]:
        raise AssertionError("run_doctor_checks must not run in e2e isolation mode")

    monkeypatch.setenv("KAGAN_E2E_TEMP_DIR", "/tmp/kagan-e2e-isolation-test")
    monkeypatch.setattr("kagan.server._system_routes.run_doctor_checks", _boom)
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    payload = json_body(response)
    data: dict[str, Any] = payload["data"]
    assert data["ok"] is True
    assert data["fail_count"] == 0
    assert data["warn_count"] == 0
    assert data["checks"] == []


def _make_checks(*statuses: str) -> list[DoctorCheck]:
    """Build minimal DoctorCheck stubs for the given statuses."""
    return [
        DoctorCheck(
            name=f"check {i}",
            status=status,
            message=f"msg {i}",
            fix_hint=f"fix {i}" if status != "pass" else "",
            verify_hint=f"verify {i}",
        )
        for i, status in enumerate(statuses)
    ]


@pytest.mark.asyncio
async def test_doctor_ok_when_all_checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/doctor returns ok=true, fail_count=0 when all checks pass."""
    checks = _make_checks("pass", "pass", "warn")
    monkeypatch.setattr(
        "kagan.server._system_routes.run_doctor_checks",
        lambda: checks,
    )
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    payload = json_body(response)
    assert payload["ok"] is True
    data: dict[str, Any] = payload["data"]
    assert data["ok"] is True
    assert data["fail_count"] == 0
    assert data["warn_count"] == 1
    assert len(data["checks"]) == 3


@pytest.mark.asyncio
async def test_doctor_not_ok_when_any_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/doctor returns ok=false and correct fail_count when a check is fail."""
    checks = _make_checks("pass", "fail", "fail", "warn")
    monkeypatch.setattr(
        "kagan.server._system_routes.run_doctor_checks",
        lambda: checks,
    )
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    payload = json_body(response)
    assert payload["ok"] is True  # HTTP envelope is always ok=True on success
    data: dict[str, Any] = payload["data"]
    assert data["ok"] is False
    assert data["fail_count"] == 2
    assert data["warn_count"] == 1


@pytest.mark.asyncio
async def test_doctor_response_shape_matches_doctor_report_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each check in the response includes all DoctorCheckResponse fields."""
    checks = _make_checks("pass", "warn", "fail")
    monkeypatch.setattr(
        "kagan.server._system_routes.run_doctor_checks",
        lambda: checks,
    )
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    data: dict[str, Any] = json_body(response)["data"]

    # Validate the aggregate shape via DoctorReportResponse
    report = DoctorReportResponse.model_validate(data)
    assert report.fail_count == 1
    assert report.warn_count == 1
    assert len(report.checks) == 3

    # Validate each check has all required fields
    required_fields = set(DoctorCheckResponse.model_fields)
    for check_dict in data["checks"]:
        assert required_fields == set(check_dict.keys()), (
            f"Check missing fields: {required_fields - set(check_dict.keys())}"
        )


@pytest.mark.asyncio
async def test_doctor_is_blocking_derived_from_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_blocking is True only for fail-status checks."""
    checks = _make_checks("pass", "warn", "fail")
    monkeypatch.setattr(
        "kagan.server._system_routes.run_doctor_checks",
        lambda: checks,
    )
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    data: dict[str, Any] = json_body(response)["data"]
    check_list = data["checks"]
    assert check_list[0]["is_blocking"] is False  # pass
    assert check_list[1]["is_blocking"] is False  # warn
    assert check_list[2]["is_blocking"] is True  # fail


@pytest.mark.asyncio
async def test_doctor_category_defaults_to_core_without_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """category falls back to 'core' when the returned object has no category attribute.

    This guard covers the period before task 623a6f913a0047db is merged.
    Uses a plain SimpleNamespace stub (no category field) so the
    getattr(c, "category", "core") branch in the handler is genuinely exercised.
    """
    from types import SimpleNamespace

    stub_checks = [
        SimpleNamespace(
            name="stub_check",
            status="pass",
            message="stub message",
            fix_hint="",
            verify_hint="",
        )
    ]
    monkeypatch.setattr(
        "kagan.server._system_routes.run_doctor_checks",
        lambda: stub_checks,
    )
    mcp = make_api_server()
    endpoint = get_http_endpoint(mcp, "/api/doctor", "GET")

    response = await endpoint(make_request("GET", "/api/doctor"))

    data: dict[str, Any] = json_body(response)["data"]
    assert data["checks"][0]["category"] == "core"


@pytest.mark.asyncio
async def test_existing_preflight_endpoint_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """/api/preflight is unmodified — responds with the legacy dict shape."""
    from types import SimpleNamespace

    mcp = make_api_server()

    async def _fake_preflight(agent_backend: str | None = None) -> list[Any]:
        return [
            SimpleNamespace(
                name="git",
                status=SimpleNamespace(value="pass"),
                message="Git ok",
                fix_hint="",
                is_blocking=False,
            )
        ]

    async def _get_settings() -> dict[str, str]:
        return {}

    fake_ctx = SimpleNamespace(
        client=SimpleNamespace(
            preflight=_fake_preflight,
            settings=SimpleNamespace(get=_get_settings),
        )
    )
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    endpoint = get_http_endpoint(mcp, "/api/preflight", "GET")
    response = await endpoint(make_request("GET", "/api/preflight"))
    payload = json_body(response)

    assert payload["ok"] is True
    assert "checks" in payload["data"]
    assert "ok" in payload["data"]
    # /api/preflight must NOT include fail_count or warn_count (legacy shape)
    assert "fail_count" not in payload["data"]
    assert "warn_count" not in payload["data"]
