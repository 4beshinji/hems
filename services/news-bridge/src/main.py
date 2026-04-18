"""
HEMS News Bridge — RSS news fetcher + Ollama summarizer + urgency detection.
Publishes daily summaries and urgent news alerts to MQTT.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from loguru import logger
from news_fetcher import NewsFetcher
from news_summarizer import NewsSummarizer, OllamaClient, split_by_category
from urgency import UrgencyDetector

import config
from mqtt_publisher import MQTTPublisher

# Module-level state
mqtt_pub: MQTTPublisher | None = None
fetcher: NewsFetcher | None = None
summarizer: NewsSummarizer | None = None
urgency_detector: UrgencyDetector | None = None
_tasks: list[asyncio.Task] = []

# Cached latest summary
_latest_summary: dict = {}
_seen_urls: set[str] = set()  # Already-checked URLs for urgency dedup


async def _generate_daily_summary():
    """Fetch articles and generate daily summary."""
    global _latest_summary
    try:
        articles = await fetcher.fetch_all()
        if not articles:
            logger.warning("No articles fetched")
            return

        summary_text = await summarizer.daily_summary(articles)
        chunks = split_by_category(summary_text)

        _latest_summary = {
            "summary": summary_text,
            "chunks": chunks,
            "article_count": len(articles),
            "timestamp": time.time(),
        }

        mqtt_pub.publish("hems/news/daily", _latest_summary)
        logger.info(f"Daily summary published: {len(articles)} articles, {len(chunks)} chunks")

    except Exception as e:
        logger.error(f"Daily summary generation failed: {e}")


async def _check_urgent_news():
    """Check for urgent news articles."""
    try:
        articles = await fetcher.fetch_all()

        for article in articles:
            if article.url in _seen_urls:
                continue
            _seen_urls.add(article.url)

            score = await urgency_detector.score(article)
            if urgency_detector.is_urgent(score):
                # Translate if needed
                translated = await summarizer.translate_if_needed(article)
                payload = {
                    "title": article.title,
                    "summary": translated[:300],
                    "score": round(score, 2),
                    "source": article.source,
                    "url": article.url,
                    "timestamp": time.time(),
                }
                mqtt_pub.publish("hems/news/urgent", payload)
                logger.info(f"Urgent news: [{score:.2f}] {article.title[:60]}")

        # Prune seen URLs set (keep last 500)
        if len(_seen_urls) > 500:
            # Keep only the most recent by clearing and re-adding the last batch
            _seen_urls.clear()

    except Exception as e:
        logger.error(f"Urgent news check failed: {e}")


async def _publish_bridge_status():
    """Publish bridge status to MQTT."""
    mqtt_pub.publish(
        "hems/news/bridge/status",
        {
            "connected": True,
            "last_fetch": _latest_summary.get("timestamp", 0),
            "articles_count": _latest_summary.get("article_count", 0),
        },
    )


async def _daily_summary_loop():
    """Scheduled daily summary generation."""
    while True:
        try:
            now = datetime.now()
            # Calculate seconds until next scheduled time
            target_hour = config.NEWS_DAILY_HOUR
            target_minute = config.NEWS_DAILY_MINUTE
            target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if now >= target:
                # Already past today's target — schedule for tomorrow
                import datetime as dt_mod

                target = target + dt_mod.timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.info(f"Next daily summary at {target.strftime('%H:%M')} ({wait_seconds:.0f}s)")
            await asyncio.sleep(wait_seconds)

            await _generate_daily_summary()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Daily summary loop error: {e}")
            await asyncio.sleep(60)


async def _urgent_check_loop():
    """Periodic urgent news check."""
    # Initial delay to let Ollama start
    await asyncio.sleep(30)
    while True:
        try:
            await _check_urgent_news()
            await _publish_bridge_status()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Urgent check loop error: {e}")
        await asyncio.sleep(config.NEWS_POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_pub, fetcher, summarizer, urgency_detector

    # MQTT
    mqtt_pub = MQTTPublisher(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_USER,
        config.MQTT_PASS,
    )
    mqtt_pub.connect()

    # Ollama client
    ollama = OllamaClient(url=config.OLLAMA_URL, model=config.OLLAMA_SUMMARY_MODEL)

    # Components
    fetcher = NewsFetcher(sources=config.NEWS_SOURCE_LIST)
    summarizer = NewsSummarizer(ollama)
    urgency_detector = UrgencyDetector(ollama, threshold=config.NEWS_URGENCY_THRESHOLD)

    # Generate initial summary on startup
    _tasks.append(asyncio.create_task(_initial_summary()))
    # Start polling loops
    _tasks.append(asyncio.create_task(_daily_summary_loop()))
    _tasks.append(asyncio.create_task(_urgent_check_loop()))

    logger.info(
        f"News Bridge started: sources={config.NEWS_SOURCE_LIST}, "
        f"daily={config.NEWS_DAILY_HOUR:02d}:{config.NEWS_DAILY_MINUTE:02d}, "
        f"poll={config.NEWS_POLL_INTERVAL}s"
    )
    yield

    for t in _tasks:
        t.cancel()
    mqtt_pub.disconnect()
    logger.info("News Bridge stopped")


async def _initial_summary():
    """Generate summary shortly after startup."""
    await asyncio.sleep(10)  # Wait for Ollama
    await _generate_daily_summary()


app = FastAPI(title="HEMS News Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "sources": config.NEWS_SOURCE_LIST,
        "has_summary": bool(_latest_summary),
    }


@app.get("/api/news/latest")
async def get_latest():
    if not _latest_summary:
        raise HTTPException(404, "No summary generated yet")
    return _latest_summary


@app.post("/api/news/refresh")
async def refresh():
    await _generate_daily_summary()
    return {"status": "ok", "summary_available": bool(_latest_summary)}
