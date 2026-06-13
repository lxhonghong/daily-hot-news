"""新闻去重：URL 去重 + 标题相似度去重"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Sequence

from Levenshtein import ratio as levenshtein_ratio

from src.collectors.rss_collector import Category, RawItem

logger = logging.getLogger(__name__)

# 标题相似度阈值：超过此值认为是同一新闻
SIMILARITY_THRESHOLD = 0.75


def deduplicate(items: list[RawItem]) -> list[RawItem]:
    """对新闻列表进行去重

    去重策略：
    1. URL 精确去重：同一 URL 只保留一条
    2. 标题相似度去重：Levenshtein 相似度 > 阈值的视为同一条
    """

    if not items:
        return items

    # 第一步：URL 精确去重
    seen_urls: set[str] = set()
    url_deduped: list[RawItem] = []

    for item in items:
        # 规范化 URL：去掉尾部斜杠和查询参数中的追踪参数
        normalized_url = item.url.rstrip("/")
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            url_deduped.append(item)

    removed_by_url = len(items) - len(url_deduped)
    if removed_by_url > 0:
        logger.info("URL 去重: 移除 %d 条重复", removed_by_url)

    # 第二步：标题相似度去重
    result: list[RawItem] = []
    seen_titles: list[str] = []

    for item in url_deduped:
        is_duplicate = False
        for seen_title in seen_titles:
            similarity = levenshtein_ratio(item.title, seen_title)
            if similarity > SIMILARITY_THRESHOLD:
                is_duplicate = True
                break

        if not is_duplicate:
            result.append(item)
            seen_titles.append(item.title)

    removed_by_title = len(url_deduped) - len(result)
    if removed_by_title > 0:
        logger.info("标题相似度去重: 移除 %d 条相似", removed_by_title)

    total_removed = removed_by_url + removed_by_title
    if total_removed > 0:
        logger.info("去重完成: %d → %d (移除 %d)", len(items), len(result), total_removed)

    return result


def deduplicate_all(
    data: dict[Category, list[RawItem]],
) -> dict[Category, list[RawItem]]:
    """对所有方向的新闻分别去重"""

    result: dict[Category, list[RawItem]] = {}
    for category, items in data.items():
        result[category] = deduplicate(items)
        logger.info(
            "去重 [%s]: %d → %d",
            category.value,
            len(items),
            len(result[category]),
        )

    return result
