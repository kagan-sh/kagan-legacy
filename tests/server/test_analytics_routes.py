from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import kagan.server._helpers as server_helpers
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

pytestmark = [pytest.mark.smoke]


class _FakeAnalytics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    async def backend_stats(self, project_id: str, days: int | None = None) -> list[dict[str, Any]]:
        self.calls.append(("backend_stats", project_id, days))
        return [{"agent_backend": "alpha", "count": 1}]

    async def session_timeline(
        self, project_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        self.calls.append(("session_timeline", project_id, days))
        return [{"date": "2026-04-28", "total": 1}]

    async def timeline_summary(self, project_id: str, days: int = 30) -> dict[str, Any]:
        self.calls.append(("timeline_summary", project_id, days))
        return {"total_sessions": 1}

    async def export(self, project_id: str, days: int = 30) -> dict[str, Any]:
        self.calls.append(("export", project_id, days))
        return {"period_days": days, "backend_stats": [], "session_timeline": []}

    async def backend_by_role_stats(
        self, project_id: str, days: int | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("backend_by_role_stats", project_id, days))
        return [{"agent_role": "worker", "agent_backend": "alpha", "count": 1}]

    async def backend_by_task_type_stats(
        self, project_id: str, days: int | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("backend_by_task_type_stats", project_id, days))
        return [{"task_type": "bug_fix", "agent_backend": "alpha", "count": 1}]

    async def backend_role_task_stats(
        self, project_id: str, days: int | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("backend_role_task_stats", project_id, days))
        return [
            {
                "agent_role": "worker",
                "task_type": "bug_fix",
                "agent_backend": "alpha",
                "count": 1,
            },
            {
                "agent_role": "reviewer",
                "task_type": "design",
                "agent_backend": "beta",
                "count": 1,
            },
        ]

    async def recommended_backend(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("recommended_backend", project_id, None))
        return {"backend": "alpha"}


def _install_context(monkeypatch: pytest.MonkeyPatch, analytics: _FakeAnalytics) -> None:
    ctx = SimpleNamespace(
        client=SimpleNamespace(
            active_project_id="project-1",
            analytics=analytics,
        ),
        opts=ServerOptions(),
    )
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: ctx)


@pytest.mark.asyncio
async def test_backend_stats_route_forwards_days_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    analytics = _FakeAnalytics()
    _install_context(monkeypatch, analytics)

    endpoint = get_http_endpoint(mcp, "/api/analytics/backend-stats", "GET")
    response = json_body(await endpoint(make_request("GET", "/api/analytics/backend-stats?days=7")))

    assert response["data"] == [{"agent_backend": "alpha", "count": 1}]
    assert analytics.calls == [("backend_stats", "project-1", 7)]


@pytest.mark.asyncio
async def test_grouped_analytics_routes_forward_days_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    analytics = _FakeAnalytics()
    _install_context(monkeypatch, analytics)

    by_role = get_http_endpoint(mcp, "/api/analytics/by-role", "GET")
    by_task_type = get_http_endpoint(mcp, "/api/analytics/by-task-type", "GET")

    role_response = json_body(await by_role(make_request("GET", "/api/analytics/by-role?days=14")))
    task_type_response = json_body(
        await by_task_type(make_request("GET", "/api/analytics/by-task-type?days=14"))
    )

    assert role_response["data"] == {
        "worker": [{"agent_role": "worker", "agent_backend": "alpha", "count": 1}]
    }
    assert task_type_response["data"] == {
        "bug_fix": [{"task_type": "bug_fix", "agent_backend": "alpha", "count": 1}]
    }
    assert analytics.calls == [
        ("backend_by_role_stats", "project-1", 14),
        ("backend_by_task_type_stats", "project-1", 14),
    ]


@pytest.mark.asyncio
async def test_combined_analytics_route_filters_after_days_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    analytics = _FakeAnalytics()
    _install_context(monkeypatch, analytics)

    endpoint = get_http_endpoint(mcp, "/api/analytics/by-role-and-task-type", "GET")
    response = json_body(
        await endpoint(
            make_request(
                "GET",
                "/api/analytics/by-role-and-task-type?days=30&role=worker&task_type=bug_fix",
            )
        )
    )

    assert response["data"] == [
        {
            "agent_role": "worker",
            "task_type": "bug_fix",
            "agent_backend": "alpha",
            "count": 1,
        }
    ]
    assert analytics.calls == [("backend_role_task_stats", "project-1", 30)]


@pytest.mark.asyncio
async def test_timeline_and_export_routes_use_requested_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    analytics = _FakeAnalytics()
    _install_context(monkeypatch, analytics)

    timeline = get_http_endpoint(mcp, "/api/analytics/session-timeline", "GET")
    summary = get_http_endpoint(mcp, "/api/analytics/timeline-summary", "GET")
    export = get_http_endpoint(mcp, "/api/analytics/export", "GET")

    timeline_response = json_body(
        await timeline(make_request("GET", "/api/analytics/session-timeline?days=3"))
    )
    summary_response = json_body(
        await summary(make_request("GET", "/api/analytics/timeline-summary?days=3"))
    )
    export_response = json_body(await export(make_request("GET", "/api/analytics/export?days=3")))

    assert timeline_response["data"] == [{"date": "2026-04-28", "total": 1}]
    assert summary_response["data"] == {"total_sessions": 1}
    assert export_response["data"]["period_days"] == 3
    assert analytics.calls == [
        ("session_timeline", "project-1", 3),
        ("timeline_summary", "project-1", 3),
        ("export", "project-1", 3),
    ]
