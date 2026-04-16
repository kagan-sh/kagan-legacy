"""Analytics queries — aggregate session data for the dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, case, func
from sqlalchemy import cast as sa_cast
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core._utils import utc_iso
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, Task


class Analytics:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def backend_stats(self, project_id: str) -> list[dict[str, Any]]:
        """Per-backend aggregates: count, success rate, avg duration, etc."""
        completed_case = case(
            (Session.status == SessionStatus.COMPLETED, 1),
            else_=0,
        )
        retry_case = case(
            (sa_cast(Session.attempt, type_=Session.attempt.type) > 1, 1),  # type: ignore[union-attr]
            else_=0,
        )
        duration_expr = func.julianday(Session.ended_at) - func.julianday(Session.started_at)

        stmt = (
            select(
                Session.agent_backend,
                func.count(Session.id).label("count"),
                func.avg(completed_case).label("success_rate"),
                func.avg(
                    case((Session.ended_at.is_not(None), duration_expr * 86400), else_=None),  # type: ignore[union-attr]
                ).label("avg_duration_seconds"),
                func.avg(retry_case).label("retry_rate"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id)
            .group_by(Session.agent_backend)
            .order_by(func.count(Session.id).desc())
        )

        def _run(s):
            rows = s.exec(stmt).all()
            return [
                {
                    "agent_backend": row[0],
                    "count": row[1],
                    "success_rate": round(float(row[2] or 0), 4),
                    "avg_duration_seconds": round(float(row[3]), 1) if row[3] is not None else None,
                    "retry_rate": round(float(row[4] or 0), 4),
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)

    async def export(self, project_id: str, days: int = 30) -> dict[str, Any]:
        """Bundle backend stats + session timeline into a single export dict."""
        stats = await self.backend_stats(project_id)
        timeline = await self.session_timeline(project_id, days=days)
        return {
            "exported_at": utc_iso(datetime.now(UTC)),
            "period_days": days,
            "backend_stats": stats,
            "session_timeline": timeline,
        }

    def export_json(self, data: dict[str, Any]) -> str:
        """Serialize an export dict to compact JSON."""
        return json.dumps(data, separators=(",", ":"))

    async def session_timeline(self, project_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Daily session counts by status."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        def _status_count(status: SessionStatus):
            return func.sum(case((Session.status == status, 1), else_=0))

        stmt = (
            select(
                func.date(Session.started_at).label("day"),
                func.count(Session.id).label("total"),
                _status_count(SessionStatus.COMPLETED).label("completed"),
                _status_count(SessionStatus.FAILED).label("failed"),
                _status_count(SessionStatus.CANCELLED).label("cancelled"),
                _status_count(SessionStatus.RUNNING).label("running"),
                _status_count(SessionStatus.PENDING).label("pending"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id, Session.started_at >= cutoff)
            .group_by(func.date(Session.started_at))
            .order_by(func.date(Session.started_at))
        )

        def _run(s):
            rows = s.exec(stmt).all()
            return [
                {
                    "date": str(row[0]),
                    "total": int(row[1]),
                    "completed": int(row[2]),
                    "failed": int(row[3]),
                    "cancelled": int(row[4]),
                    "running": int(row[5]),
                    "pending": int(row[6]),
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)

    async def timeline_summary(
        self, project_id: str, days: int = 30
    ) -> dict[str, int | float]:
        """Aggregate timeline data into summary statistics."""
        timeline = await self.session_timeline(project_id, days=days)

        total_sessions = sum(d["total"] for d in timeline)
        total_completed = sum(d["completed"] for d in timeline)
        total_failed = sum(d["failed"] for d in timeline)
        total_cancelled = sum(d["cancelled"] for d in timeline)
        active_days = sum(1 for d in timeline if d["total"] > 0)

        success_rate = (
            total_completed / total_sessions if total_sessions > 0 else 0
        )

        return {
            "total_sessions": total_sessions,
            "total_completed": total_completed,
            "total_failed": total_failed,
            "total_cancelled": total_cancelled,
            "active_days": active_days,
            "success_rate": round(float(success_rate), 4),
        }

    async def recommended_backend(self, project_id: str) -> dict[str, Any]:
        """Get the backend with the highest success rate (if any sessions exist)."""
        stats = await self.backend_stats(project_id)
        if not stats:
            return {}
        # Return backend with highest success rate
        best = max(stats, key=lambda s: s["success_rate"])
        return {
            "backend": best["agent_backend"],
            "success_rate": best["success_rate"],
            "count": best["count"],
        }

    async def backend_by_role_stats(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Per-backend, per-agent-role aggregates."""
        completed_case = case(
            (Session.status == SessionStatus.COMPLETED, 1),
            else_=0,
        )
        duration_expr = func.julianday(Session.ended_at) - func.julianday(
            Session.started_at
        )

        stmt = (
            select(
                Session.agent_backend,
                Session.agent_role,
                func.count(Session.id).label("count"),
                func.avg(completed_case).label("success_rate"),
                func.avg(
                    case(
                        (Session.ended_at.is_not(None), duration_expr * 86400),
                        else_=None,
                    ),
                ).label("avg_duration_seconds"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id)
            .group_by(Session.agent_backend, Session.agent_role)
            .order_by(func.count(Session.id).desc())
        )

        def _run(s):
            rows = s.exec(stmt).all()
            return [
                {
                    "agent_backend": row[0],
                    "agent_role": row[1],
                    "count": row[2],
                    "success_rate": round(float(row[3] or 0), 4),
                    "avg_duration_seconds": round(float(row[4]), 1)
                    if row[4] is not None
                    else None,
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)

    async def backend_by_task_type_stats(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Per-backend, per-task-type aggregates."""
        completed_case = case(
            (Session.status == SessionStatus.COMPLETED, 1),
            else_=0,
        )
        duration_expr = func.julianday(Session.ended_at) - func.julianday(
            Session.started_at
        )

        stmt = (
            select(
                Session.agent_backend,
                Task.task_type,
                func.count(Session.id).label("count"),
                func.avg(completed_case).label("success_rate"),
                func.avg(
                    case(
                        (Session.ended_at.is_not(None), duration_expr * 86400),
                        else_=None,
                    ),
                ).label("avg_duration_seconds"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id)
            .group_by(Session.agent_backend, Task.task_type)
            .order_by(func.count(Session.id).desc())
        )

        def _run(s):
            rows = s.exec(stmt).all()
            return [
                {
                    "agent_backend": row[0],
                    "task_type": row[1],
                    "count": row[2],
                    "success_rate": round(float(row[3] or 0), 4),
                    "avg_duration_seconds": round(float(row[4]), 1)
                    if row[4] is not None
                    else None,
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)

    async def backend_role_task_stats(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Per-backend, per-agent-role, per-task-type aggregates (fully dimensional)."""
        completed_case = case(
            (Session.status == SessionStatus.COMPLETED, 1),
            else_=0,
        )
        duration_expr = func.julianday(Session.ended_at) - func.julianday(
            Session.started_at
        )

        stmt = (
            select(
                Session.agent_backend,
                Session.agent_role,
                Task.task_type,
                func.count(Session.id).label("count"),
                func.avg(completed_case).label("success_rate"),
                func.avg(
                    case(
                        (Session.ended_at.is_not(None), duration_expr * 86400),
                        else_=None,
                    ),
                ).label("avg_duration_seconds"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id)
            .group_by(Session.agent_backend, Session.agent_role, Task.task_type)
            .order_by(func.count(Session.id).desc())
        )

        def _run(s):
            rows = s.exec(stmt).all()
            return [
                {
                    "agent_backend": row[0],
                    "agent_role": row[1],
                    "task_type": row[2],
                    "count": row[3],
                    "success_rate": round(float(row[4] or 0), 4),
                    "avg_duration_seconds": round(float(row[5]), 1)
                    if row[5] is not None
                    else None,
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)
