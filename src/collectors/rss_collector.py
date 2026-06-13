"""RSS 采集器：并发采集所有 RSS 源（RSSHub + 原生 RSS）"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import feedparser
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class Category(str, Enum):
    """新闻方向分类"""

    AI_TECH = "ai_tech"
    INTERNATIONAL = "international"
    DOMESTIC = "domestic"


@dataclass(frozen=True)
class FeedSource:
    """RSS 数据源定义"""

    name: str
    url: str
    category: Category
    # 是否需要代理访问（国际源走宿主机代理）
    needs_proxy: bool = False


@dataclass(frozen=True)
class RawItem:
    """采集到的原始新闻条目"""

    title: str
    url: str
    summary: str
    source_name: str
    category: Category
    published: str = ""


# ===== 所有 RSS 数据源 =====
FEED_SOURCES: list[FeedSource] = [
    # --- AI/科技方向 ---
    FeedSource("36氪热榜", "{rsshub}/36kr/hot-list/24", Category.AI_TECH),
    FeedSource("量子位", "{rsshub}/qbitai/category/资讯", Category.AI_TECH),
    FeedSource("Hacker News", "https://hnrss.org/best", Category.AI_TECH, needs_proxy=True),
    FeedSource("TechCrunch", "{rsshub}/techcrunch/news", Category.AI_TECH),
    FeedSource("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI", Category.AI_TECH),
    FeedSource("arXiv cs.CL", "https://rss.arxiv.org/rss/cs.CL", Category.AI_TECH),
    # --- 国际形势方向 ---
    FeedSource("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", Category.INTERNATIONAL, needs_proxy=True),
    FeedSource("BBC 中文网", "{rsshub}/bbc/chinese", Category.INTERNATIONAL),
    # --- 国内形势方向 ---
    FeedSource("知乎热榜", "{rsshub}/zhihu/hot", Category.DOMESTIC),
    FeedSource("澎湃新闻", "{rsshub}/thepaper/featured", Category.DOMESTIC),
    FeedSource("观察者网", "{rsshub}/guancha/headline", Category.DOMESTIC),
    FeedSource("人民网", "{rsshub}/people", Category.DOMESTIC),
]


def _resolve_url(url: str) -> str:
    """将 {rsshub} 占位符替换为实际 RSSHub 地址"""
    return url.replace("{rsshub}", settings.rsshub_base_url)


async def _fetch_one(
    client: httpx.AsyncClient,
    source: FeedSource,
) -> list[RawItem]:
    """采集单个 RSS feed，返回解析后的条目列表"""

    url = _resolve_url(source.url)

    try:
        response = await client.get(url, timeout=settings.rss_timeout)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("采集失败 [%s]: %s", source.name, exc)
        return []

    # feedparser 从字符串解析
    feed = feedparser.parse(response.text)

    if not feed.entries:
        logger.info("无条目 [%s]", source.name)
        return []

    items: list[RawItem] = []
    for entry in feed.entries[:30]:  # 每个源最多取 30 条
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()
        published = entry.get("published", entry.get("updated", ""))

        if not title or not link:
            continue

        items.append(
            RawItem(
                title=title,
                url=link,
                summary=summary,
                source_name=source.name,
                category=source.category,
                published=published,
            )
        )

    logger.info("采集完成 [%s]: %d 条", source.name, len(items))
    return items


async def collect_all_feeds() -> dict[Category, list[RawItem]]:
    """并发采集所有 RSS 源，按分类分组返回"""

    start = time.monotonic()

    # 分两组 client：国内源直连，国际源走代理
    domestic_client = httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "DailyHotNews/0.1"},
    )
    international_client = httpx.AsyncClient(
        follow_redirects=True,
        proxy=settings.http_proxy,
        headers={"User-Agent": "DailyHotNews/0.1"},
    )

    results: dict[Category, list[RawItem]] = {
        Category.AI_TECH: [],
        Category.INTERNATIONAL: [],
        Category.DOMESTIC: [],
    }

    try:
        tasks = []
        for source in FEED_SOURCES:
            client = international_client if source.needs_proxy else domestic_client
            tasks.append(_fetch_one(client, source))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for source, result in zip(FEED_SOURCES, raw_results):
            if isinstance(result, Exception):
                logger.warning("采集异常 [%s]: %s", source.name, result)
                continue
            if isinstance(result, list):
                results[source.category] = results[source.category] + result
    finally:
        await domestic_client.aclose()
        await international_client.aclose()

    elapsed = time.monotonic() - start
    total = sum(len(v) for v in results.values())
    logger.info(
        "RSS 采集完成: 共 %d 条 (AI/科技 %d, 国际 %d, 国内 %d), 耗时 %.1fs",
        total,
        len(results[Category.AI_TECH]),
        len(results[Category.INTERNATIONAL]),
        len(results[Category.DOMESTIC]),
        elapsed,
    )

    return results
