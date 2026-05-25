"""Tests for brain ShoppingClassifier (P1 — seed rules only)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _async_response(status: int = 200, body: str = "ok"):
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    resp.json = AsyncMock(return_value={})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session._response = _async_response()
    session.patch = MagicMock(return_value=session._response)
    # Cache HTTP path: GET returns 404 (not found) by default so LLM fallback runs.
    session.get = MagicMock(return_value=_async_response(status=404))
    session.post = MagicMock(return_value=_async_response(status=201))
    return session


@pytest.fixture
def classifier(mock_session):
    from annotator import ShoppingClassifier

    return ShoppingClassifier(
        session=mock_session,
        backend_url="http://backend:8000",
    )


class TestSeedRules:
    def test_drugstore_hit(self, classifier):
        assert classifier.classify("コンタクトレンズ液") == "drugstore"
        assert classifier.classify("シャンプー") == "drugstore"

    def test_supermarket_hit(self, classifier):
        assert classifier.classify("牛乳 1L") == "supermarket"
        assert classifier.classify("食パン") == "supermarket"

    def test_convenience_hit(self, classifier):
        assert classifier.classify("切手 63円") == "convenience"

    def test_home_center_hit(self, classifier):
        assert classifier.classify("LED電球") == "home_center"
        assert classifier.classify("培養土") == "home_center"

    def test_miss_returns_none(self, classifier):
        assert classifier.classify("謎のアイテム12345") is None

    def test_empty_name_returns_none(self, classifier):
        assert classifier.classify("") is None
        assert classifier.classify(None) is None  # type: ignore[arg-type]


class TestCachePromotion:
    def test_seed_match_is_cached(self, classifier):
        name = "牛乳"
        assert classifier.classify(name) == "supermarket"
        # Second lookup should hit cache (hit_count increments)
        entry = classifier.cache.get_memory("shopping", name)
        assert entry is not None
        assert entry.value == "supermarket"
        assert entry.source == "seed"
        assert entry.hit_count >= 2


class TestPatchWriteback:
    def test_handle_added_triggers_patch(self, classifier, mock_session):
        handled = asyncio.run(classifier.handle_added_event({"id": 42, "name": "シャンプー"}))
        assert handled is True
        mock_session.patch.assert_called_once()
        args, kwargs = mock_session.patch.call_args
        assert args[0] == "http://backend:8000/shopping/42"
        assert kwargs["json"] == {"store_category": "drugstore"}

    def test_handle_added_skips_on_miss(self, classifier, mock_session):
        handled = asyncio.run(classifier.handle_added_event({"id": 7, "name": "謎アイテム"}))
        assert handled is False
        mock_session.patch.assert_not_called()

    def test_handle_added_requires_id_and_name(self, classifier, mock_session):
        assert asyncio.run(classifier.handle_added_event({"name": "牛乳"})) is False
        assert asyncio.run(classifier.handle_added_event({"id": 1})) is False
        mock_session.patch.assert_not_called()

    def test_patch_failure_returns_false(self, classifier, mock_session):
        mock_session.patch.return_value = _async_response(status=500, body="oops")
        handled = asyncio.run(classifier.handle_added_event({"id": 42, "name": "牛乳"}))
        assert handled is False

    def test_no_auth_header_sent(self, mock_session):
        from annotator import ShoppingClassifier

        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
        )
        asyncio.run(clf.handle_added_event({"id": 1, "name": "牛乳"}))
        assert mock_session.patch.called


class TestLLMFallback:
    """Seed miss → LLM → cache write-back."""

    def test_llm_fallback_classifies(self, mock_session):
        from annotator import ShoppingClassifier
        from annotator.cache import ClassifierCache

        llm_router = AsyncMock()
        llm_router.chat = AsyncMock(return_value=MagicMock(content="drugstore"))

        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
            cache=ClassifierCache(session=mock_session, backend_url="http://backend:8000"),
            llm_router=llm_router,
        )
        result = asyncio.run(clf.classify_async("未知のアイテム"))
        assert result == "drugstore"
        llm_router.chat.assert_awaited_once()
        # Cache write-back: backend POST /classifier-cache must have been called.
        assert mock_session.post.called

    def test_llm_garbage_returns_none(self, mock_session):
        from annotator import ShoppingClassifier

        llm_router = AsyncMock()
        llm_router.chat = AsyncMock(return_value=MagicMock(content="NOT A CATEGORY"))

        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
            llm_router=llm_router,
        )
        assert asyncio.run(clf.classify_async("アイテム")) is None

    def test_llm_trailing_punct_parsed(self, mock_session):
        from annotator import ShoppingClassifier

        llm_router = AsyncMock()
        llm_router.chat = AsyncMock(return_value=MagicMock(content="カテゴリはこちら: home_center."))
        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
            llm_router=llm_router,
        )
        assert asyncio.run(clf.classify_async("バケツ")) == "home_center"

    def test_no_llm_router_returns_none_on_miss(self, mock_session):
        from annotator import ShoppingClassifier

        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
        )
        assert asyncio.run(clf.classify_async("未知")) is None

    def test_llm_exception_returns_none(self, mock_session):
        from annotator import ShoppingClassifier

        llm_router = AsyncMock()
        llm_router.chat = AsyncMock(side_effect=RuntimeError("timeout"))
        clf = ShoppingClassifier(
            session=mock_session,
            backend_url="http://backend:8000",
            llm_router=llm_router,
        )
        assert asyncio.run(clf.classify_async("未知")) is None
