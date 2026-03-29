"""Client presence tracking for cross-client awareness.

Tracks connected clients via heartbeat. Presence is ephemeral (in-memory only)
and auto-expires after missed heartbeats.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ClientPresence:
    """A connected client's presence record."""

    client_id: str
    client_type: str  # "web", "vscode", "tui", "chat", "mcp"
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    active_task_id: str | None = None
    user_label: str = ""

    def is_alive(self, timeout: float = 60.0) -> bool:
        """Check if presence is still valid (heartbeat within timeout)."""
        return (time.time() - self.last_heartbeat) < timeout


class PresenceTracker:
    """In-memory presence tracker. Thread-safe via GIL for simple dict operations."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientPresence] = {}

    def register(
        self,
        client_id: str,
        client_type: str,
        user_label: str = "",
        active_task_id: str | None = None,
    ) -> ClientPresence:
        """Register or update a client's presence."""
        if client_id in self._clients:
            presence = self._clients[client_id]
            presence.last_heartbeat = time.time()
            presence.active_task_id = active_task_id
            if user_label:
                presence.user_label = user_label
        else:
            presence = ClientPresence(
                client_id=client_id,
                client_type=client_type,
                user_label=user_label,
                active_task_id=active_task_id,
            )
            self._clients[client_id] = presence
        return presence

    def heartbeat(self, client_id: str, active_task_id: str | None = None) -> None:
        """Update heartbeat timestamp for a client."""
        if client_id in self._clients:
            self._clients[client_id].last_heartbeat = time.time()
            if active_task_id is not None:
                self._clients[client_id].active_task_id = active_task_id

    def unregister(self, client_id: str) -> None:
        """Remove a client's presence."""
        self._clients.pop(client_id, None)

    def list_active(self, timeout: float = 60.0) -> list[ClientPresence]:
        """List all clients with recent heartbeats."""
        expired = [cid for cid, p in self._clients.items() if not p.is_alive(timeout)]
        for cid in expired:
            del self._clients[cid]
        return list(self._clients.values())

    def watchers_for_task(self, task_id: str, timeout: float = 60.0) -> list[ClientPresence]:
        """List clients actively watching a specific task."""
        return [p for p in self.list_active(timeout) if p.active_task_id == task_id]

    def to_wire(self, timeout: float = 60.0) -> list[dict[str, Any]]:
        """Serialize active presence for API responses."""
        return [
            {
                "client_id": p.client_id,
                "client_type": p.client_type,
                "connected_at": p.connected_at,
                "active_task_id": p.active_task_id,
                "user_label": p.user_label,
            }
            for p in self.list_active(timeout)
        ]
