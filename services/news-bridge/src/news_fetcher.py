"""RSS news fetcher — ported from voisona-yomiage."""

from dataclasses import dataclass, field
from datetime import datetime

import aiohttp
import feedparser
from loguru import logger

RSS_SOURCES = {
    "nhk_main": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "nhk_international": "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
}


@dataclass
class Article:
    """ニュース記事."""

    title: str
    summary: str
    url: str
    source: str
    published: datetime | None = None
    language: str = "ja"
    metadata: dict = field(default_factory=dict)


class NewsFetcher:
    """RSSフィードからニュース記事を取得."""

    def __init__(self, sources: list[str] | None = None):
        self.source_names = sources or list(RSS_SOURCES.keys())

    async def fetch_all(self) -> list[Article]:
        """全ソースから記事を取得."""
        articles: list[Article] = []
        for name in self.source_names:
            url = RSS_SOURCES.get(name)
            if not url:
                logger.warning(f"Unknown news source: {name}")
                continue
            try:
                new_articles = await self._fetch_feed(name, url)
                articles.extend(new_articles)
            except Exception as e:
                logger.error(f"Failed to fetch {name}: {e}")
        return articles

    async def _fetch_feed(self, source_name: str, feed_url: str) -> list[Article]:
        async with (
            aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "hems-news-bridge/0.1"},
            ) as session,
            session.get(feed_url) as resp,
        ):
            if resp.status != 200:
                raise RuntimeError(f"RSS fetch failed: {resp.status}")
            text = await resp.text()

        feed = feedparser.parse(text)
        articles = []

        lang = "ja" if "nhk" in source_name else "en"

        for entry in feed.entries[:20]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            articles.append(
                Article(
                    title=entry.get("title", ""),
                    summary=entry.get("summary", entry.get("description", "")),
                    url=entry.get("link", ""),
                    source=source_name,
                    published=published,
                    language=lang,
                )
            )

        logger.info(f"Fetched {len(articles)} articles from {source_name}")
        return articles
