"""Analytics queries — aggregate session and cost data for the dashboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, case, func
from sqlalchemy import cast as sa_cast
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, Task


class Analytics:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def backend_stats(self, project_id: str) -> list[dict[str, Any]]:
        """Per-backend aggregates: count, success rate, avg cost, avg duration, etc."""
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
                func.avg(Session.cost_amount).label("avg_cost"),
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
                    "avg_cost": round(float(row[3] or 0), 6),
                    "avg_duration_seconds": round(float(row[4]), 1) if row[4] is not None else None,
                    "human_override_rate": 0.0,
                    "retry_rate": round(float(row[5] or 0), 4),
                }
                for row in rows
            ]

        return await _db_async(self._engine, _run)

    async def cost_summary(self, project_id: str, days: int = 30) -> dict[str, Any]:
        """Cost breakdown: total, by day, and by backend."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        stmt_by_day = (
            select(
                func.date(Session.started_at).label("day"),
                func.coalesce(func.sum(Session.cost_amount), 0).label("cost"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id, Session.started_at >= cutoff)
            .group_by(func.date(Session.started_at))
            .order_by(func.date(Session.started_at))
        )

        stmt_by_backend = (
            select(
                Session.agent_backend,
                func.coalesce(func.sum(Session.cost_amount), 0).label("cost"),
            )
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id, Session.started_at >= cutoff)
            .group_by(Session.agent_backend)
            .order_by(func.sum(Session.cost_amount).desc())
        )

        stmt_total = (
            select(func.coalesce(func.sum(Session.cost_amount), 0))
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id, Session.started_at >= cutoff)
        )

        def _run(s):
            total = s.exec(stmt_total).one()
            by_day = s.exec(stmt_by_day).all()
            by_backend = s.exec(stmt_by_backend).all()
            return {
                "total_cost": round(float(total or 0), 6),
                "cost_by_day": {str(row[0]): round(float(row[1]), 6) for row in by_day},
                "cost_by_backend": {row[0]: round(float(row[1]), 6) for row in by_backend},
            }

        return await _db_async(self._engine, _run)

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
