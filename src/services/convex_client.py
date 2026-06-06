"""Minimal Convex HTTP client."""

from dataclasses import dataclass
from typing import Any

import httpx


class ConvexApiError(RuntimeError):
    """Raised when the Convex API returns an unsuccessful response."""


@dataclass
class ConvexClient:
    base_url: str
    sync_token: str
    http_client: httpx.AsyncClient
    timeout_seconds: float = 10.0

    def _build_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.sync_token}",
            "Content-Type": "application/json",
        }

    def _build_get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.sync_token}",
        }

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.post(
            self._build_url(path),
            headers=self._build_headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code != 200:
            raise ConvexApiError(f"Convex API request failed with status {response.status_code}: {response.text}")

        return response.json()

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.get(
            self._build_url(path),
            headers=self._build_get_headers(),
            params={key: value for key, value in params.items() if value is not None},
            timeout=self.timeout_seconds,
        )

        if response.status_code != 200:
            raise ConvexApiError(f"Convex API request failed with status {response.status_code}: {response.text}")

        return response.json()

    def post_sync(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            self._build_url(path),
            headers=self._build_headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code != 200:
            raise ConvexApiError(f"Convex API request failed with status {response.status_code}: {response.text}")

        return response.json()

    def get_sync(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = httpx.get(
            self._build_url(path),
            headers=self._build_get_headers(),
            params={key: value for key, value in params.items() if value is not None},
            timeout=self.timeout_seconds,
        )

        if response.status_code != 200:
            raise ConvexApiError(f"Convex API request failed with status {response.status_code}: {response.text}")

        return response.json()

    async def healthcheck(self) -> bool:
        try:
            response = await self.http_client.get(
                self._build_url("/health"),
                headers={"Authorization": f"Bearer {self.sync_token}"},
                timeout=self.timeout_seconds,
            )
        except (httpx.HTTPError, RuntimeError):
            return False

        return response.status_code == 200
