"""Async HTTP client for Shelly RPC API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shelly_exporter.config import Credentials

logger = logging.getLogger(__name__)


class ShellyClientError(Exception):
    """Base exception for Shelly client errors."""

    pass


class ShellyAuthError(ShellyClientError):
    """Authentication failed (401/403)."""

    pass


class ShellyTimeoutError(ShellyClientError):
    """Request timed out."""

    pass


class ShellyClient:
    """Async HTTP client for Shelly devices using JSON-RPC API.

    Uses HTTP POST to /rpc endpoint with JSON-RPC format.
    """

    def __init__(
        self,
        base_url: str,
        credentials: Credentials | None = None,
        timeout: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize Shelly client.

        Args:
            base_url: Device URL (e.g., "10.0.80.22" or "http://10.0.80.22")
            credentials: Optional authentication credentials
            timeout: Request timeout in seconds
            client: Optional shared httpx client for connection pooling
        """
        # Normalize URL
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None
        self._request_id = 0

    async def __aenter__(self) -> ShellyClient:
        if self._owns_client:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    def _get_auth(self) -> httpx.BasicAuth | None:
        """Get HTTP Basic Auth if credentials are configured."""
        if self.credentials and self.credentials.has_credentials():
            return httpx.BasicAuth(
                username=self.credentials.username,
                password=self.credentials.password,
            )
        return None

    async def _rpc_call(self, method: str) -> dict[str, Any]:
        """Make a JSON-RPC call to the device.

        Args:
            method: RPC method name (e.g., "Shelly.GetStatus")

        Returns:
            The "result" field from the RPC response

        Raises:
            ShellyAuthError: On 401/403 response
            ShellyTimeoutError: On timeout
            ShellyClientError: On other errors
        """
        if self._client is None:
            raise ShellyClientError("Client not initialized. Use async context manager.")

        self._request_id += 1
        url = f"{self.base_url}/rpc"
        payload = {"id": self._request_id, "method": method}

        try:
            response = await self._client.post(
                url,
                json=payload,
                auth=self._get_auth(),
            )

            if response.status_code in (401, 403):
                raise ShellyAuthError(f"Authentication failed: {response.status_code}")

            response.raise_for_status()
            data = response.json()

            if "error" in data:
                error = data["error"]
                raise ShellyClientError(
                    f"RPC error {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"
                )

            return data.get("result", {})

        except httpx.TimeoutException as e:
            raise ShellyTimeoutError(f"Request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ShellyAuthError(f"Authentication failed: {e.response.status_code}") from e
            raise ShellyClientError(f"HTTP error: {e}") from e
        except httpx.RequestError as e:
            raise ShellyClientError(f"Request error: {e}") from e

    async def get_device_info(self) -> dict[str, Any]:
        """Get device information.

        Returns:
            Device info dict containing model, gen, app, etc.
        """
        return await self._rpc_call("Shelly.GetDeviceInfo")

    async def get_status(self) -> dict[str, Any]:
        """Get device status.

        Returns:
            Status dict containing channel data (switch:0, light:0, etc.)
        """
        return await self._rpc_call("Shelly.GetStatus")


class ShellyClientPool:
    """Pool of Shelly clients sharing a single httpx client for connection reuse."""

    def __init__(self, timeout: float = 3.0, max_connections: int = 100) -> None:
        """Initialize client pool.

        Args:
            timeout: Request timeout in seconds
            max_connections: Maximum concurrent connections
        """
        self.timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._max_connections = max_connections

    async def __aenter__(self) -> ShellyClientPool:
        self._http_client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(
                max_connections=self._max_connections,
                max_keepalive_connections=self._max_connections // 2,
            ),
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_client(
        self,
        base_url: str,
        credentials: Credentials | None = None,
    ) -> ShellyClient:
        """Get a client for a specific device.

        Args:
            base_url: Device URL
            credentials: Optional credentials

        Returns:
            ShellyClient instance using the shared HTTP client
        """
        return ShellyClient(
            base_url=base_url,
            credentials=credentials,
            timeout=self.timeout,
            client=self._http_client,
        )
