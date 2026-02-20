"""SDK transport layer for communicating with Kagan core."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from kagan.core.ipc.client import IPCClient
from kagan.core.ipc.discovery import CoreEndpoint, discover_core_endpoint
from kagan.sdk._errors import ConnectionError, CoreFailureError, TimeoutError

if TYPE_CHECKING:
    from kagan.core.constants import CapabilityProfile

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_AUTH_FAILED_CODE = "AUTH_FAILED"
_MAX_ATTEMPTS = 3


class SDKTransport:
    """Transport layer for the SDK.

    Wraps the IPC client and handles connection lifecycle.
    Includes automatic retry with reconnection/endpoint rediscovery.
    """

    def __init__(
        self,
        endpoint: CoreEndpoint | None = None,
        *,
        client: IPCClient | None = None,
        session_id: str = "sdk-session",
        session_origin: str = "sdk",
        client_version: str = "0.0.0",
        capability_profile: CapabilityProfile | str = "operator",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._session_id = session_id
        self._session_origin = session_origin
        self._client_version = client_version
        self._capability_profile = capability_profile
        self._timeout = timeout
        self._client = client if (client is not None and client.is_connected) else None
        self._endpoint = endpoint
        self._recover_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Connect to the Kagan core."""
        if self._client is not None and self._client.is_connected:
            return

        endpoint = self._endpoint
        if endpoint is None:
            endpoint = await asyncio.to_thread(discover_core_endpoint)

        if endpoint is None:
            raise ConnectionError(
                "Cannot discover Kagan core endpoint. Ensure Kagan core is running."
            )

        self._client = IPCClient(endpoint, timeout=self._timeout)
        try:
            await self._client.connect()
        except Exception as exc:
            self._client = None
            msg = "Failed to connect to Kagan core."
            hint = "Ensure Kagan core is running and reachable."
            raise ConnectionError(f"{msg} {hint}") from exc

    async def close(self) -> None:
        """Close the transport connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> SDKTransport:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _refresh_client_from_discovery(self) -> bool:
        """Discover a new endpoint and replace the current client."""
        endpoint = await asyncio.to_thread(discover_core_endpoint)
        if endpoint is None:
            return False

        new_client = IPCClient(endpoint, timeout=self._timeout)
        try:
            await new_client.connect()
        except Exception:
            with suppress(Exception):
                await new_client.close()
            return False

        if self._client is not None:
            with suppress(Exception):
                await self._client.close()
        self._client = new_client
        self._endpoint = endpoint
        return True

    async def _recover_client(self, *, refresh_endpoint: bool) -> bool:
        """Attempt to recover the IPC connection.

        If *refresh_endpoint* is True, skip reconnecting the current client
        and go straight to endpoint rediscovery.  Otherwise try a plain
        reconnect first, falling back to rediscovery on failure.
        """
        async with self._recover_lock:
            if refresh_endpoint:
                return await self._refresh_client_from_discovery()
            if self._client is not None:
                try:
                    await self._client.connect()
                except Exception:
                    return await self._refresh_client_from_discovery()
                return bool(self._client.is_connected)
            return await self._refresh_client_from_discovery()

    async def request(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Send a request to the core with automatic retry and reconnection.

        Up to 3 attempts are made.  On transport errors the client is
        reconnected (or a fresh endpoint is discovered).  ``AUTH_FAILED``
        responses trigger endpoint rediscovery before retrying.

        Args:
            capability: The capability (e.g., 'tasks', 'projects')
            method: The method name within the capability
            params: Optional parameters for the method
            request_timeout_seconds: Optional timeout override

        Returns:
            The response dictionary from the core

        Raises:
            ConnectionError: If not connected to the core
            TimeoutError: If the request times out
            CoreFailureError: If the core returns an error
        """
        if self._client is None or not self._client.is_connected:
            if not await self._recover_client(refresh_endpoint=False):
                raise ConnectionError("Not connected to Kagan core. Call connect() first.")

        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.request(
                    session_id=self._session_id,
                    session_profile=self._capability_profile,
                    session_origin=self._session_origin,
                    client_version=self._client_version,
                    capability=capability,
                    method=method,
                    params=params or {},
                    request_timeout_seconds=request_timeout_seconds,
                )
            except Exception as exc:
                if attempt < _MAX_ATTEMPTS - 1 and await self._recover_client(
                    refresh_endpoint=False
                ):
                    continue
                if isinstance(exc, TimeoutError):
                    raise TimeoutError(f"Request to {capability}.{method} timed out") from exc
                raise ConnectionError(f"Connection lost: {exc}") from exc

            if response.ok:
                return response.result or {}

            error = response.error
            code = error.code if error else "UNKNOWN"
            message = str(error.message).strip() if error and error.message else ""
            if not message:
                message = f"{capability}.{method} request failed"

            if code == _AUTH_FAILED_CODE and attempt < _MAX_ATTEMPTS - 1:
                if await self._recover_client(refresh_endpoint=True):
                    continue
                raise CoreFailureError(
                    "MCP session token became stale after core restart. "
                    "Restart MCP or reconnect client to re-authenticate.",
                    code="AUTH_STALE_TOKEN",
                    capability=capability,
                    method=method,
                )

            raise CoreFailureError(
                message,
                code=code,
                capability=capability,
                method=method,
            )

        raise CoreFailureError(
            "unexpected retry state",
            code="UNKNOWN",
            capability=capability,
            method=method,
        )

    async def query(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Send a query (read-only) request to the core.

        Alias for request() - the distinction between query and command
        is handled internally by the core.
        """
        return await self.request(
            capability,
            method,
            params,
            request_timeout_seconds=request_timeout_seconds,
        )


__all__ = ["SDKTransport"]
