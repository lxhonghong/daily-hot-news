"""CurrentsAPI 采集器：补充英文/中文新闻搜索"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.collectors.rss_collector import Category, RawItem
from src.config import settings

logger = logging.getLogger(__name__)


# CurrentsAPI 搜索参数：按方向定义
CURRENTS_QUERIES: dict[Category, dict[str, str]] = {
    Category.AI_TECH: {
        "keywords": "AI artificial intelligence technology",
        "category": "technology",
        "language": "en",
    },
    Category.INTERNATIONAL: {
        "category": "world",
        "language": "en",
    },
    Category.DOMESTIC: {
        "country": "CN",
        "language": "zh",
    },
}


async def _fetch_currents(
    client: httpx.AsyncClient,
    category: Category,
    params: dict[str, str],
) -> list[RawItem]:
    """采集单个 CurrentsAPI 查询"""

    if not settings.currents_api_key:
        logger.info("CurrentsAPI Key 未配置，跳过 [%s]", category.value)
        return []

    url = "https://api.currentsapi.services/v1/search"
    headers = {"Authorization": settings.currents_api_key}
    query = {**params, "page_size": "20"}

    try:
        response = await client.get(
            url,
            params=query,
            headers=headers,
            timeout=settings.currents_timeout,
        )
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("CurrentsAPI 采集失败 [%s]: %s", category.value, exc)
        return []

    data = response.json()
    articles = data.get("news", [])

    items: list[RawItem] = []
    for article in articles[:20]:
        title = article.get("title", "").strip()
        url = article.get("url", "").strip()
        summary = article.get("description", "").strip()
        source_name = article.get("source", "CurrentsAPI")

        if not title or not url:
            continue

        items.append(
            RawItem(
                title=title,
                url=url,
                summary=summary,
                source_name=source_name,
                category=category,
            )
        )

    logger.info("CurrentsAPI [%s]: %d 条", category.value, len(items))
    return items


async def collect_currents() -> dict[Category, list[RawItem]]:
    """采集 CurrentsAPI 三个方向的数据"""

    start = time.monotonic()

    # CurrentsAPI 是国际 API，走代理
    client = httpx.AsyncClient(
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
        tasks = [
            _fetch_currents(client, category, params)
            for category, params in CURRENTS_QUERIES.items()
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for category, result in zip(CURRENTS_QUERIES.keys(), raw_results):
            if isinstance(result, Exception):
                logger.warning("CurrentsAPI 异常 [%s]: %s", category.value, result)
                continue
            if isinstance(result, list):
                results[category] = result
    finally:
        await client.aclose()

    elapsed = time.monotonic() - start
    total = sum(len(v) for v in results.values())
    logger.info("CurrentsAPI 采集完成: 共 %d 条, 耗时 %.1fs", total, elapsed)

    return results
