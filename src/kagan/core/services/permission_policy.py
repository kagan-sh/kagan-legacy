"""Compatibility shim for legacy permission-policy imports.

The canonical implementation lives in ``kagan.core.policy``.
"""

from __future__ import annotations

from kagan.core.policy import (
    AgentPermissionScope,
    PermissionDecision,
    PermissionDecisionReason,
    resolve_auto_approve,
    resolve_permission_decision,
)

__all__ = [
    "AgentPermissionScope",
    "PermissionDecision",
    "PermissionDecisionReason",
    "resolve_auto_approve",
    "resolve_permission_decision",
]
