"""GitHub Trending + Search API 采集器：AI 项目飙升榜"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Any

import httpx

from src.collectors.rss_collector import Category, RawItem
from src.config import settings

logger = logging.getLogger(__name__)

# GitHub Trending CDN 数据源（isboyjc/github-trending-api）
TRENDING_CDN_URLS: list[dict[str, str]] = [
    {"name": "GitHub Trending Python", "url": "https://cdn.jsdelivr.net/gh/isboyjc/github-trending-api/data/daily/python.json"},
    {"name": "GitHub Trending Jupyter", "url": "https://cdn.jsdelivr.net/gh/isboyjc/github-trending-api/data/daily/jupyter-notebook.json"},
]

# GitHub Search API 查询（核心 AI：模型/框架）
GITHUB_SEARCH_QUERIES: list[dict[str, str]] = [
    {
        "name": "AI 框架 Star 排名",
        "query": "topic:large-language-models sort:stars",
        "sort": "stars",
        "order": "desc",
    },
    {
        "name": "近一周活跃 AI 项目",
        "query_template": "LLM OR transformer OR diffusion stars:>100 pushed:>{date_week_ago}",
        "sort": "stars",
        "order": "desc",
    },
]

GITHUB_API_BASE = "https://api.github.com"


async def _fetch_trending_cdn(
    client: httpx.AsyncClient,
    source: dict[str, str],
) -> list[RawItem]:
    """从 CDN 获取 GitHub Trending JSON 数据"""

    url = source["url"]
    source_name = source["name"]

    try:
        response = await client.get(url, timeout=settings.rss_timeout)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Trending CDN 采集失败 [%s]: %s", source_name, exc)
        return []

    try:
        data = response.json()
    except Exception:
        logger.warning("Trending CDN JSON 解析失败 [%s]", source_name)
        return []

    # CDN 数据格式：顶层是对象，items 字段是数组
    if isinstance(data, dict) and "items" in data:
        repos = data["items"]
    elif isinstance(data, list):
        repos = data
    else:
        logger.warning("Trending CDN 数据格式异常 [%s]: 顶层类型=%s", source_name, type(data).__name__)
        return []

    items: list[RawItem] = []
    for repo in repos:
        # CDN 格式：title="author/name", description, stars 是字符串
        title = repo.get("title", "")
        url = repo.get("url", "")
        description = repo.get("description", "") or ""
        stars = repo.get("stars", "0")
        add_stars = repo.get("addStars", "0")
        language = repo.get("language", "")

        # 兼容另一种格式：author + name 分离
        if not title:
            author = repo.get("author", "")
            name = repo.get("name", "")
            title = f"{author}/{name}" if author and name else ""
            url = url or f"https://github.com/{author}/{name}"
            stars = repo.get("stars", "0")
            add_stars = repo.get("currentPeriodStars", "0")

        if not title or not url:
            continue

        # 清理 stars 格式（可能带逗号 "13,967"）
        stars_clean = str(stars).replace(",", "")
        add_stars_clean = str(add_stars).replace(",", "")

        summary = f"{description} | ⭐ {stars} (+{add_stars_clean}/day) | Lang: {language}"

        items.append(
            RawItem(
                title=title,
                url=url,
                summary=summary.strip(" |"),
                source_name=source_name,
                category=Category.AI_GITHUB,
            )
        )

    logger.info("Trending CDN [%s]: %d 条", source_name, len(items))
    return items


async def _fetch_github_search(
    client: httpx.AsyncClient,
    query_info: dict[str, str],
) -> list[RawItem]:
    """调用 GitHub Search API 获取仓库数据"""

    source_name = query_info["name"]

    # 处理动态日期模板
    query = query_info.get("query", "")
    if not query:
        template = query_info.get("query_template", "")
        if template:
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            query = template.replace("{date_week_ago}", week_ago)

    if not query:
        return []

    params = {
        "q": query,
        "sort": query_info.get("sort", "stars"),
        "order": query_info.get("order", "desc"),
        "per_page": "15",
    }

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "DailyHotNews/0.1",
    }

    # 如果配置了 GitHub Token，添加认证
    if settings.github_token:
        headers["Authorization"] = f"token {settings.github_token}"

    url = f"{GITHUB_API_BASE}/search/repositories"

    try:
        response = await client.get(
            url,
            params=params,
            headers=headers,
            timeout=settings.rss_timeout,
        )
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("GitHub Search 采集失败 [%s]: %s", source_name, exc)
        return []

    try:
        data = response.json()
    except Exception:
        logger.warning("GitHub Search JSON 解析失败 [%s]", source_name)
        return []

    repos = data.get("items", [])
    if not repos:
        logger.info("GitHub Search [%s]: 无结果", source_name)
        return []

    items: list[RawItem] = []
    for repo in repos:
        full_name = repo.get("full_name", "")
        description = repo.get("description", "") or ""
        html_url = repo.get("html_url", "")
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language", "")
        topics = repo.get("topics", [])

        if not full_name or not html_url:
            continue

        topics_str = ", ".join(topics[:5]) if topics else ""
        summary = f"{description} | ⭐ {stars} | Lang: {language}"
        if topics_str:
            summary += f" | Topics: {topics_str}"

        items.append(
            RawItem(
                title=full_name,
                url=html_url,
                summary=summary.strip(" |"),
                source_name=source_name,
                category=Category.AI_GITHUB,
            )
        )

    logger.info("GitHub Search [%s]: %d 条", source_name, len(items))
    return items


async def collect_github_trending() -> dict[Category, list[RawItem]]:
    """采集 GitHub Trending + Search API 数据"""

    start = time.monotonic()

    # CDN 走代理（jsdelivr 在国内可能慢）
    cdn_client = httpx.AsyncClient(
        follow_redirects=True,
        proxy=settings.http_proxy,
        headers={"User-Agent": "DailyHotNews/0.1"},
    )

    # GitHub API 也走代理
    api_client = httpx.AsyncClient(
        follow_redirects=True,
        proxy=settings.http_proxy,
        headers={"User-Agent": "DailyHotNews/0.1"},
    )

    results: dict[Category, list[RawItem]] = {
        Category.AI_GITHUB: [],
    }

    try:
        # 并发采集所有数据源
        tasks = []

        # CDN 数据源
        for source in TRENDING_CDN_URLS:
            tasks.append(_fetch_trending_cdn(cdn_client, source))

        # GitHub Search API
        for query_info in GITHUB_SEARCH_QUERIES:
            tasks.append(_fetch_github_search(api_client, query_info))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in raw_results:
            if isinstance(result, Exception):
                logger.warning("GitHub Trending 采集异常: %s", result)
                continue
            if isinstance(result, list):
                results[Category.AI_GITHUB] = results[Category.AI_GITHUB] + result

    finally:
        await cdn_client.aclose()
        await api_client.aclose()

    elapsed = time.monotonic() - start
    total = sum(len(v) for v in results.values())
    logger.info("GitHub Trending 采集完成: 共 %d 条, 耗时 %.1fs", total, elapsed)

    return results
