"""Async client for backend /thresholds API."""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from brain_constants import backend_auth_headers

BACKEND_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)


class ThresholdClientError(Exception):
    pass


class ThresholdClient:
    """Thin async client wrapping backend /thresholds endpoints."""

    def __init__(self, backend_url: str | None = None, session: aiohttp.ClientSession | None = None):
        self.backend_url = backend_url or BACKEND_URL
        self._http_session = session
        self._owned_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self):
        if self._owned_session and self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        session = await self._get_session()
        url = f"{self.backend_url}/thresholds{path}"
        try:
            async with session.request(
                method,
                url,
                headers=backend_auth_headers(),
                json=json,
                params=params,
                timeout=DEFAULT_TIMEOUT,
            ) as resp:
                body = await resp.json() if resp.content_type == "application/json" else await resp.text()
                if resp.status >= 400:
                    raise ThresholdClientError(f"HTTP {resp.status}: {body}")
                return body
        except aiohttp.ClientError as e:
            raise ThresholdClientError(f"request failed: {e}") from e

    async def create_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("POST", "/proposals", json=proposal)
        if not isinstance(result, dict):
            raise ThresholdClientError(f"unexpected response type: {type(result)}")
        return result

    async def list_proposals(
        self,
        status: str | None = None,
        metric_key: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if metric_key:
            params["metric_key"] = metric_key
        result = await self._request("GET", "/proposals", params=params or None)
        if not isinstance(result, list):
            raise ThresholdClientError(f"unexpected response type: {type(result)}")
        return result

    async def decide_proposal(
        self,
        proposal_id: int,
        decision: str,
        reviewer_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        payload = {"decision": decision}
        if reviewer_id:
            payload["reviewer_id"] = reviewer_id
        if reason:
            payload["reason"] = reason
        result = await self._request("POST", f"/proposals/{proposal_id}/decide", json=payload)
        if not isinstance(result, dict):
            raise ThresholdClientError(f"unexpected response type: {type(result)}")
        return result

    async def list_adjustments(self, metric_key: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if metric_key:
            params["metric_key"] = metric_key
        result = await self._request("GET", "/adjustments", params=params or None)
        if not isinstance(result, list):
            raise ThresholdClientError(f"unexpected response type: {type(result)}")
        return result

    async def create_adjustment(self, adjustment: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("POST", "/adjustments", json=adjustment)
        if not isinstance(result, dict):
            raise ThresholdClientError(f"unexpected response type: {type(result)}")
        return result
