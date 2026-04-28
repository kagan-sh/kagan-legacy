"""Analytics queries — aggregate session data for the dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, case, func
from sqlalchemy import cast as sa_cast
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async
from kagan.core._utils import utc_iso
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, Task, TelemetryEvent


async def emit_telemetry(engine: Engine, event_type: str, payload: dict[str, Any]) -> None:
    """Persist a system-level telemetry event not tied to any task or session."""
    event = TelemetryEvent(event_type=event_type, payload=payload)
    await _db_async(engine, lambda s: _add_and_refresh(s, event))


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
        """Daily session counts by status, plus doctor_warned and first_session_success counts."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        def _status_count(status: SessionStatus):
            return func.sum(case((Session.status == status, 1), else_=0))

        sessions_stmt = (
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

        telemetry_stmt = (
            select(
                func.date(TelemetryEvent.created_at).label("day"),
                func.sum(
                    case(
                        (TelemetryEvent.event_type == "DOCTOR_WARNED", 1),
                        else_=0,
                    )
                ).label("doctor_warned_count"),
                func.sum(
                    case(
                        (TelemetryEvent.event_type == "FIRST_SESSION_SUCCESS", 1),
                        else_=0,
                    )
                ).label("first_session_success_count"),
            )
            .where(TelemetryEvent.created_at >= cutoff)
            .group_by(func.date(TelemetryEvent.created_at))
        )

        def _run(s):
            rows = s.exec(sessions_stmt).all()
            result_by_day: dict[str, dict[str, Any]] = {
                str(row[0]): {
                    "date": str(row[0]),
                    "total": int(row[1]),
                    "completed": int(row[2]),
                    "failed": int(row[3]),
                    "cancelled": int(row[4]),
                    "running": int(row[5]),
                    "pending": int(row[6]),
                    "doctor_warned_count": 0,
                    "first_session_success_count": 0,
                }
                for row in rows
            }

            for trow in s.exec(telemetry_stmt).all():
                day_key = str(trow[0])
                warned = int(trow[1] or 0)
                success = int(trow[2] or 0)
                if day_key in result_by_day:
                    result_by_day[day_key]["doctor_warned_count"] = warned
                    result_by_day[day_key]["first_session_success_count"] = success
                else:
                    result_by_day[day_key] = {
                        "date": day_key,
                        "total": 0,
                        "completed": 0,
                        "failed": 0,
                        "cancelled": 0,
                        "running": 0,
                        "pending": 0,
                        "doctor_warned_count": warned,
                        "first_session_success_count": success,
                    }

            return sorted(result_by_day.values(), key=lambda r: r["date"])

        return await _db_async(self._engine, _run)

    async def timeline_summary(self, project_id: str, days: int = 30) -> dict[str, int | float]:
        """Aggregate timeline data into summary statistics."""
        timeline = await self.session_timeline(project_id, days=days)

        total_sessions = sum(d["total"] for d in timeline)
        total_completed = sum(d["completed"] for d in timeline)
        total_failed = sum(d["failed"] for d in timeline)
        total_cancelled = sum(d["cancelled"] for d in timeline)
        active_days = sum(1 for d in timeline if d["total"] > 0)

        success_rate = total_completed / total_sessions if total_sessions > 0 else 0

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

    async def _aggregate_stats(
        self,
        project_id: str,
        group_by_role: bool = False,
        group_by_task_type: bool = False,
    ) -> list[dict[str, Any]]:
        """Unified aggregation across dimensions: backend, role, task_type.

        Args:
            project_id: Project to aggregate for
            group_by_role: Include agent_role in grouping and results
            group_by_task_type: Include task_type in grouping and results

        Returns:
            List of dicts with agent_backend, optional agent_role, optional task_type,
            count, success_rate, and avg_duration_seconds
        """
        completed_case = case(
            (Session.status == SessionStatus.COMPLETED, 1),
            else_=0,
        )
        duration_expr = func.julianday(Session.ended_at) - func.julianday(Session.started_at)

        # Build select columns dynamically
        select_cols = [
            Session.agent_backend,
        ]
        group_cols = [Session.agent_backend]

        if group_by_role:
            select_cols.append(Session.agent_role)
            group_cols.append(Session.agent_role)

        if group_by_task_type:
            select_cols.append(Task.task_type)
            group_cols.append(Task.task_type)

        select_cols.extend(
            [
                func.count(Session.id).label("count"),
                func.avg(completed_case).label("success_rate"),
                func.avg(
                    case(
                        (Session.ended_at.is_not(None), duration_expr * 86400),
                        else_=None,
                    ),
                ).label("avg_duration_seconds"),
            ]
        )

        stmt = (
            select(*select_cols)
            .join(Task, Task.id == Session.task_id)
            .where(Task.project_id == project_id)
            .group_by(*group_cols)
            .order_by(func.count(Session.id).desc())
        )

        def _run(s):
            rows = s.exec(stmt).all()
            results = []

            for row in rows:
                mapping = row._mapping
                result: dict[str, Any] = {"agent_backend": mapping["agent_backend"]}

                if group_by_role:
                    result["agent_role"] = mapping["agent_role"]

                if group_by_task_type:
                    result["task_type"] = mapping["task_type"]

                result["count"] = mapping["count"]
                result["success_rate"] = round(float(mapping["success_rate"] or 0), 4)
                raw_duration = mapping["avg_duration_seconds"]
                result["avg_duration_seconds"] = (
                    round(float(raw_duration), 1) if raw_duration is not None else None
                )
                results.append(result)

            return results

        return await _db_async(self._engine, _run)

    async def backend_by_role_stats(self, project_id: str) -> list[dict[str, Any]]:
        """Per-backend, per-agent-role aggregates."""
        return await self._aggregate_stats(project_id, group_by_role=True)

    async def backend_by_task_type_stats(self, project_id: str) -> list[dict[str, Any]]:
        """Per-backend, per-task-type aggregates."""
        return await self._aggregate_stats(project_id, group_by_task_type=True)

    async def backend_role_task_stats(self, project_id: str) -> list[dict[str, Any]]:
        """Per-backend, per-agent-role, per-task-type aggregates (fully dimensional)."""
        return await self._aggregate_stats(project_id, group_by_role=True, group_by_task_type=True)
