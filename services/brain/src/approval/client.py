"""Async client for backend approvals API.

Used by the Brain approval gate to create approval requests, poll for human
decisions, record action snapshots, and mark actions executed.
"""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from brain_constants import backend_auth_headers

BACKEND_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)


class ApprovalClientError(Exception):
    pass


class ApprovalClient:
    """Thin async client wrapping backend /approvals endpoints."""

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
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.backend_url}/approvals{path}"
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
                    raise ApprovalClientError(f"HTTP {resp.status}: {body}")
                return body if isinstance(body, dict) else {"raw": body}
        except aiohttp.ClientError as e:
            raise ApprovalClientError(f"request failed: {e}") from e

    async def create(
        self,
        action_type: str,
        proposed_payload: dict,
        risk_tier: str = "low",
        reversibility: str = "reversible",
        context: dict | None = None,
        rule_id: int | None = None,
        thread_id: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        payload = {
            "action_type": action_type,
            "risk_tier": risk_tier,
            "reversibility": reversibility,
            "proposed_payload": proposed_payload,
            "context": context or {},
        }
        if rule_id is not None:
            payload["rule_id"] = rule_id
        if thread_id is not None:
            payload["thread_id"] = thread_id
        if confidence is not None:
            payload["confidence"] = confidence
        return await self._request("POST", "/", json=payload)

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", f"/{approval_id}")
        except ApprovalClientError as e:
            if "404" in str(e):
                return None
            raise

    async def poll_decision(
        self,
        approval_id: str,
        timeout_seconds: float = 300,
        poll_interval: float = 2,
    ) -> dict[str, Any]:
        """Poll until the approval leaves pending/proposed or timeout elapses."""
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            approval = await self.get(approval_id)
            if approval is None:
                raise ApprovalClientError(f"approval {approval_id} disappeared")
            status = approval.get("status", "")
            if status not in {"proposed", "pending"}:
                return approval
            await asyncio.sleep(poll_interval)
        approval = await self.get(approval_id)
        if approval and approval.get("status") in {"proposed", "pending"}:
            approval["status"] = "expired"
        return approval or {"status": "expired", "id": approval_id}

    async def record_snapshot(
        self,
        approval_id: str,
        entity_type: str,
        entity_id: str,
        before_state: dict,
        after_state: dict | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/{approval_id}/snapshots",
            json={
                "approval_id": approval_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before_state": before_state,
                "after_state": after_state or {},
            },
        )

    async def mark_executed(self, approval_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/{approval_id}/execute")

    async def record_rollback(
        self,
        approval_id: str,
        trigger: str,
        status: str = "success",
        error_message: str | None = None,
    ) -> dict[str, Any]:
        params = {"trigger": trigger, "status": status}
        if error_message:
            params["error_message"] = error_message
        return await self._request("POST", f"/{approval_id}/rollback", params=params)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
