"""采集测试脚本：单独验证各数据源采集是否正常"""

import asyncio
import logging
import sys

from src.collectors.rss_collector import Category, collect_all_feeds, FEED_SOURCES
from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def test_rss_collection() -> None:
    """测试 RSS 采集"""

    print("=" * 60)
    print("数据源清单")
    print("=" * 60)
    for source in FEED_SOURCES:
        proxy_tag = " [代理]" if source.needs_proxy else ""
        print(f"  {source.category.value:15s} | {source.name}{proxy_tag}")
    print()

    print("=" * 60)
    print("开始采集...")
    print("=" * 60)

    results = await collect_all_feeds()

    print()
    print("=" * 60)
    print("采集结果汇总")
    print("=" * 60)

    for category in Category:
        items = results[category]
        print(f"\n【{category.value}】共 {len(items)} 条")
        for i, item in enumerate(items[:5], 1):
            title = item.title[:60] + "..." if len(item.title) > 60 else item.title
            print(f"  {i}. [{item.source_name}] {title}")
        if len(items) > 5:
            print(f"  ... 还有 {len(items) - 5} 条")

    total = sum(len(v) for v in results.values())
    print(f"\n总计: {total} 条")

    # 检查每个方向至少有内容
    for category in Category:
        count = len(results[category])
        if count == 0:
            logger.warning("⚠️  %s 方向无任何数据!", category.value)
        elif count < 5:
            logger.warning("⚠️  %s 方向数据偏少 (%d 条)", category.value, count)
        else:
            logger.info("✅ %s 方向数据正常 (%d 条)", category.value, count)


if __name__ == "__main__":
    asyncio.run(test_rss_collection())
