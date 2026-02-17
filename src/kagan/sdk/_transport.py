"""SDK transport layer for communicating with Kagan core."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kagan.core.ipc.client import IPCClient
from kagan.core.ipc.discovery import CoreEndpoint, discover_core_endpoint
from kagan.sdk._errors import ConnectionError, CoreFailureError, TimeoutError

if TYPE_CHECKING:
    from kagan.core.constants import CapabilityProfile

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class SDKTransport:
    """Transport layer for the SDK.

    Wraps the IPC client and handles connection lifecycle.
    """

    def __init__(
        self,
        endpoint: CoreEndpoint | None = None,
        *,
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
        self._client: IPCClient | None = None
        self._endpoint = endpoint

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
            endpoint = discover_core_endpoint()

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

    async def request(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Send a request to the core.

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
            raise ConnectionError("Not connected to Kagan core. Call connect() first.")

        try:
            response = await self._client.request(
                session_id=self._session_id,
                session_origin=self._session_origin,
                client_version=self._client_version,
                capability=capability,
                method=method,
                params=params or {},
                request_timeout_seconds=request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise TimeoutError(f"Request to {capability}.{method} timed out") from exc
        except ConnectionError as exc:
            raise ConnectionError(f"Connection lost: {exc}") from exc
        except Exception as exc:
            raise ConnectionError(f"Request failed: {exc}") from exc

        if not response.ok:
            error = response.error
            raise CoreFailureError(
                error.message if error else "Unknown error",
                code=error.code if error else "UNKNOWN",
                capability=capability,
                method=method,
            )

        return response.result or {}

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
