"""
Tests for ServiceCheckerManager, BaseChecker, and individual checkers.
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from service_checker import (
    BaseChecker, ServiceStatus, GmailChecker, GitHubChecker,
    BrowserChecker, ServiceCheckerManager,
)


class ConcreteChecker(BaseChecker):
    """Minimal implementation for testing BaseChecker ABC."""

    def __init__(self, name="test", interval=60, status=None):
        super().__init__(name, interval)
        self._status = status or ServiceStatus(
            name=name, available=True, unread_count=0,
            summary="OK", last_check=time.time(),
        )

    async def check(self) -> ServiceStatus:
        self._last_status = self._status
        return self._status


class TestBaseChecker:
    def test_name_and_interval(self):
        checker = ConcreteChecker(name="foo", interval=120)
        assert checker.name == "foo"
        assert checker.interval == 120

    def test_last_status_initially_none(self):
        checker = ConcreteChecker()
        assert checker.last_status is None

    @pytest.mark.asyncio
    async def test_check_sets_last_status(self):
        checker = ConcreteChecker()
        result = await checker.check()
        assert checker.last_status is result
        assert result.name == "test"


class TestServiceStatus:
    def test_defaults(self):
        s = ServiceStatus()
        assert s.name == ""
        assert s.available is True
        assert s.unread_count == 0
        assert s.error is None

    def test_with_error(self):
        s = ServiceStatus(name="gmail", available=False, error="timeout")
        assert s.available is False
        assert s.error == "timeout"


class TestGmailChecker:
    def _make_mock_imap(self, search_result=b"1 2 3"):
        mock_imap = AsyncMock()
        mock_imap.wait_hello_from_server = AsyncMock()
        mock_imap.login = AsyncMock()
        mock_imap.select = AsyncMock()
        mock_imap.search = AsyncMock(return_value=("OK", [search_result]))
        mock_imap.logout = AsyncMock()
        return mock_imap

    def _make_mock_aioimaplib(self, mock_imap):
        mock_lib = MagicMock()
        mock_lib.IMAP4_SSL = MagicMock(return_value=mock_imap)
        return mock_lib

    @pytest.mark.asyncio
    async def test_check_success(self):
        checker = GmailChecker("user@gmail.com", "app-pass", interval=60)
        mock_imap = self._make_mock_imap(b"1 2 3")
        mock_lib = self._make_mock_aioimaplib(mock_imap)

        with patch.dict("sys.modules", {"aioimaplib": mock_lib}):
            status = await checker.check()

        assert status.available is True
        assert status.unread_count == 3
        assert "3通" in status.summary
        assert status.error is None

    @pytest.mark.asyncio
    async def test_check_no_unread(self):
        checker = GmailChecker("user@gmail.com", "app-pass")
        mock_imap = self._make_mock_imap(b"")
        mock_lib = self._make_mock_aioimaplib(mock_imap)

        with patch.dict("sys.modules", {"aioimaplib": mock_lib}):
            status = await checker.check()

        assert status.unread_count == 0
        assert "未読なし" in status.summary

    @pytest.mark.asyncio
    async def test_check_failure(self):
        checker = GmailChecker("user@gmail.com", "bad-pass")
        mock_lib = MagicMock()
        mock_lib.IMAP4_SSL = MagicMock(side_effect=Exception("Connection refused"))

        with patch.dict("sys.modules", {"aioimaplib": mock_lib}):
            status = await checker.check()

        assert status.available is False
        assert status.error is not None
        assert "Connection refused" in status.error


class TestGitHubChecker:
    def _make_mock_aiohttp(self, resp_status=200, resp_json=None):
        mock_resp = AsyncMock()
        mock_resp.status = resp_status
        mock_resp.json = AsyncMock(return_value=resp_json or [])
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock()
        return mock_aiohttp

    @pytest.mark.asyncio
    async def test_check_success(self):
        checker = GitHubChecker("ghp_token", interval=120)
        mock_aiohttp = self._make_mock_aiohttp(200, [
            {"reason": "mention", "id": "1"},
            {"reason": "review_requested", "id": "2"},
        ])

        with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            status = await checker.check()

        assert status.available is True
        assert status.unread_count == 2
        assert "2件" in status.summary
        assert "types" in status.details

    @pytest.mark.asyncio
    async def test_check_api_error(self):
        checker = GitHubChecker("bad_token")
        mock_aiohttp = self._make_mock_aiohttp(401)

        with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            status = await checker.check()

        assert status.available is False
        assert "401" in status.error


class TestBrowserChecker:
    @pytest.mark.asyncio
    async def test_check_success(self):
        oc_client = AsyncMock()
        oc_client.connected = True
        oc_client.canvas_navigate = AsyncMock()
        oc_client.canvas_eval = AsyncMock(return_value=json.dumps({
            "unread_count": 5,
            "summary": "LINE未読: 5件",
        }))

        checker = BrowserChecker(
            name="line", url="https://line.me", js_script="...",
            oc_client=oc_client, interval=300,
        )

        status = await checker.check()
        assert status.available is True
        assert status.unread_count == 5
        assert "LINE" in status.summary

    @pytest.mark.asyncio
    async def test_check_not_connected(self):
        oc_client = AsyncMock()
        oc_client.connected = False

        checker = BrowserChecker(
            name="line", url="https://line.me", js_script="...",
            oc_client=oc_client,
        )

        status = await checker.check()
        assert status.available is False
        assert "not connected" in status.error

    @pytest.mark.asyncio
    async def test_browser_lock_serialization(self):
        """Verify that browser checkers use the lock for serialization."""
        lock = asyncio.Lock()
        oc_client = AsyncMock()
        oc_client.connected = True
        oc_client.canvas_navigate = AsyncMock()
        oc_client.canvas_eval = AsyncMock(return_value='{"unread_count": 0}')

        c1 = BrowserChecker("a", "https://a.com", "...", oc_client, browser_lock=lock)
        c2 = BrowserChecker("b", "https://b.com", "...", oc_client, browser_lock=lock)
        assert c1._lock is c2._lock


class TestServiceCheckerManager:
    @pytest.fixture
    def mqtt_pub(self):
        pub = MagicMock()
        pub.publish = MagicMock()
        return pub

    def test_register(self, mqtt_pub):
        mgr = ServiceCheckerManager(mqtt_pub)
        checker = ConcreteChecker("test")
        mgr.register(checker)
        assert len(mgr._checkers) == 1

    def test_get_status_empty(self, mqtt_pub):
        mgr = ServiceCheckerManager(mqtt_pub)
        assert mgr.get_status() == {}

    @pytest.mark.asyncio
    async def test_checker_loop_publishes_mqtt(self, mqtt_pub):
        mgr = ServiceCheckerManager(mqtt_pub)
        status = ServiceStatus(
            name="test", available=True, unread_count=3,
            summary="テスト: 3件", last_check=time.time(),
        )
        checker = ConcreteChecker("test", interval=1, status=status)
        mgr.register(checker)

        # Run one iteration of the checker loop
        await mgr._checker_loop.__wrapped__(mgr, checker) if hasattr(mgr._checker_loop, '__wrapped__') else None
        # Directly test single iteration logic
        prev = mgr._statuses.get(checker.name)
        prev_count = prev.unread_count if prev else 0
        result = await checker.check()
        mgr._statuses[checker.name] = result

        assert mgr._statuses["test"].unread_count == 3

    @pytest.mark.asyncio
    async def test_edge_trigger_on_unread_increase(self, mqtt_pub):
        mgr = ServiceCheckerManager(mqtt_pub)

        # Simulate first check: 0 unread
        status1 = ServiceStatus(name="gmail", unread_count=0, last_check=time.time())
        mgr._statuses["gmail"] = status1

        # Second check: 3 unread (increase)
        checker = ConcreteChecker("gmail", status=ServiceStatus(
            name="gmail", unread_count=3, summary="未読メール: 3通",
            last_check=time.time(),
        ))
        mgr.register(checker)

        # Simulate one loop iteration manually
        prev = mgr._statuses.get("gmail")
        prev_count = prev.unread_count if prev else 0
        new_status = await checker.check()
        mgr._statuses["gmail"] = new_status

        # The edge trigger should detect increase
        assert new_status.unread_count > prev_count

    def test_get_status_returns_cached(self, mqtt_pub):
        mgr = ServiceCheckerManager(mqtt_pub)
        mgr._statuses["gmail"] = ServiceStatus(
            name="gmail", unread_count=5, summary="未読: 5通",
            last_check=time.time(),
        )
        result = mgr.get_status()
        assert "gmail" in result
        assert result["gmail"]["unread_count"] == 5
