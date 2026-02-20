"""IPC client that connects to a running Kagan core and sends requests."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from kagan.core.ipc.constants import MAX_LINE_BYTES
from kagan.core.ipc.contracts import CoreRequest, CoreResponse
from kagan.core.ipc.transports import DefaultTransport, TCPLoopbackTransport, UnixSocketTransport

if TYPE_CHECKING:
    from kagan.core.ipc.discovery import CoreEndpoint

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class IPCClient:
    """Async IPC client for communicating with the Kagan core process."""

    def __init__(
        self,
        endpoint: CoreEndpoint,
        *,
        transport: TCPLoopbackTransport | UnixSocketTransport | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._endpoint = endpoint
        self._transport = transport or self._transport_for_endpoint(endpoint)
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> IPCClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def is_connected(self) -> bool:
        """Whether the client currently holds an open connection."""
        return self._writer is not None and not self._writer.is_closing()

    @property
    def endpoint(self) -> CoreEndpoint:
        """Endpoint descriptor currently used by this client."""
        return self._endpoint

    async def connect(self) -> None:
        """Open a connection to the core."""
        if self.is_connected:
            return

        ep = self._endpoint
        if isinstance(self._transport, TCPLoopbackTransport):
            self._reader, self._writer = await self._transport.connect(
                ep.address,
                ep.port,
                handshake_token=ep.token,
            )
        else:
            self._reader, self._writer = await self._transport.connect(
                ep.address,
                ep.port,
            )
        logger.debug(
            "IPC client connected: transport=%s address=%s",
            ep.transport,
            ep.address,
        )

    async def close(self) -> None:
        """Close the connection to the core."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writer = None
            self._reader = None
            logger.debug("IPC client disconnected")

    async def reconnect(self, endpoint: CoreEndpoint) -> None:
        """Close current connection and swap to a new endpoint."""
        await self.close()
        self._endpoint = endpoint
        self._transport = self._transport_for_endpoint(endpoint)

    async def request(
        self,
        *,
        session_id: str,
        session_profile: str | None = None,
        session_origin: str,
        client_version: str,
        client_build_hash: str | None = None,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_timeout_seconds: float | None = None,
    ) -> CoreResponse:
        """Send a request to the core and return the response."""
        if not self.is_connected or self._reader is None or self._writer is None:
            msg = "Client is not connected; call connect() first"
            raise ConnectionError(msg)

        req = CoreRequest(
            session_id=session_id,
            session_profile=session_profile,
            session_origin=session_origin,
            client_version=client_version,
            client_build_hash=client_build_hash,
            capability=capability,
            method=method,
            params=params or {},
            idempotency_key=idempotency_key,
        )

        payload: dict[str, Any] = req.model_dump()
        payload["bearer_token"] = self._endpoint.token

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        effective_timeout = (
            self._timeout if request_timeout_seconds is None else request_timeout_seconds
        )

        async with self._lock:
            self._writer.write(line.encode("utf-8"))
            await self._writer.drain()

            try:
                raw = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=effective_timeout,
                )
            except ValueError as exc:
                await self.close()
                msg = "IPC response exceeded stream framing limit"
                raise ConnectionError(msg) from exc
            except TimeoutError:
                await self.close()
                raise

        if not raw:
            await self.close()
            msg = "Connection closed by server"
            raise ConnectionError(msg)
        if len(raw) > MAX_LINE_BYTES:
            await self.close()
            msg = "IPC response exceeded max line size"
            raise ConnectionError(msg)

        try:
            response = CoreResponse.model_validate_json(raw)
        except Exception as exc:
            await self.close()
            msg = "Invalid response from server"
            raise ConnectionError(msg) from exc

        if response.request_id != req.request_id:
            await self.close()
            msg = (
                "Response request_id mismatch: "
                f"expected {req.request_id}, got {response.request_id}"
            )
            raise ConnectionError(msg)

        return response

    @staticmethod
    def _transport_for_endpoint(
        endpoint: CoreEndpoint,
    ) -> TCPLoopbackTransport | UnixSocketTransport:
        """Derive the correct transport from an endpoint descriptor."""
        if endpoint.transport == "tcp":
            return TCPLoopbackTransport()
        if endpoint.transport == "socket":
            return UnixSocketTransport()
        return DefaultTransport()


__all__ = ["IPCClient"]
