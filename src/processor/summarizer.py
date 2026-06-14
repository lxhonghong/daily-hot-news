"""摘要生成器：3 个方向独立 prompt + 结构化 JSON 输出解析"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.collectors.rss_collector import Category, RawItem
from src.config import settings
from src.processor.llm import get_llm_client

logger = logging.getLogger(__name__)


# ===== 结构化输出模型 =====


@dataclass(frozen=True)
class NewsItem:
    """处理后的新闻条目"""

    title: str
    summary: str
    impact: str
    importance: int  # 1-5 星
    source: str
    url: str


@dataclass(frozen=True)
class ProcessedCategory:
    """处理后的某个方向"""

    label: str
    items: list[NewsItem]


# ===== 方向标签映射 =====

CATEGORY_LABELS: dict[Category, str] = {
    Category.AI_TECH: "AI / 科技",
    Category.INTERNATIONAL: "国际形势",
    Category.DOMESTIC: "国内形势",
    Category.DEV_TOOLS: "编程工具",
    Category.AI_GITHUB: "AI 开源飙升榜",
}


# ===== Prompt 模板 =====

PROMPT_TEMPLATES: dict[Category, str] = {
    Category.AI_TECH: """你是一位资深科技行业分析师。以下是今日 AI/科技 领域的新闻条目。

任务：
1. 去重合并：将重复或高度相似的新闻合并为一条
2. 中文摘要：为每条新闻写 2-3 句摘要，关键技术术语保留英文原文（如 LLM、GPT、Transformer、RAG、AGI、MCP、GPU、TPU、RLHF、SFT 等）
3. 影响分析：用 1 句话分析对行业或技术发展的潜在影响
4. 重要性评级：1-5 星（5 = 重大突破/行业变革，3 = 重要进展，1 = 一般资讯）

输出严格 JSON 数组，不要任何额外文本、markdown 代码块或解释：
[
  {{
    "title": "中文标题",
    "summary": "摘要内容...",
    "impact": "影响分析...",
    "importance": 4,
    "source": "来源名称",
    "url": "原始链接"
  }}
]

今日新闻条目：
---
{news_items}
---""",
    Category.INTERNATIONAL: """你是一位国际关系分析师。以下是今日国际形势领域的新闻条目。

任务：
1. 去重合并：将同一事件的多篇报道合并
2. 中文摘要：2-3 句摘要，人物/组织/地名/条约名保留英文（如 NATO、G7、EU、AUKUS、ASEAN、Zelenskyy、Xi Jinping 等）
3. 影响分析：1 句话分析对地缘格局、国际关系、全球经济的潜在影响
4. 重要性评级：1-5 星（5 = 可能改变国际格局，3 = 重要动态，1 = 一般动态）

输出严格 JSON 数组，不要任何额外文本、markdown 代码块或解释：
[
  {{
    "title": "中文标题",
    "summary": "摘要内容...",
    "impact": "影响分析...",
    "importance": 4,
    "source": "来源名称",
    "url": "原始链接"
  }}
]

今日新闻条目：
---
{news_items}
---""",
    Category.DOMESTIC: """你是一位中国公共政策和经济分析师。以下是今日国内形势领域的新闻条目。

任务：
1. 去重合并：将同一事件的多篇报道合并
2. 中文摘要：2-3 句摘要，政策/机构/企业名保留英文缩写（如 PBOC、NPC、GDP、CPI、SEC、CSI 等）
3. 影响分析：1 句话分析对经济、政策、社会的潜在影响
4. 重要性评级：1-5 星（5 = 重大政策/事件，3 = 重要动态，1 = 一般动态）

输出严格 JSON 数组，不要任何额外文本、markdown 代码块或解释：
[
  {{
    "title": "中文标题",
    "summary": "摘要内容...",
    "impact": "影响分析...",
    "importance": 4,
    "source": "来源名称",
    "url": "原始链接"
  }}
]

今日新闻条目：
---
{news_items}
---""",
    Category.DEV_TOOLS: """你是一位资深开发者工具分析师。以下是今日编程工具/IDE/语言领域的动态。

任务：
1. 去重合并：将同一工具的多条更新合并为一条
2. 中文摘要：2-3 句摘要，工具名/版本号保留英文（如 VS Code 1.99、JetBrains Rider 2026.1、Python 3.14、Rust 1.88 等）
3. 影响分析：1 句话分析对开发者工作流或生态的影响
4. 重要性评级：1-5 星（5 = 重大版本/生态变化，3 = 值得关注，1 = 小更新）

输出严格 JSON 数组，不要任何额外文本、markdown 代码块或解释：
[
  {{
    "title": "中文标题",
    "summary": "摘要内容...",
    "impact": "影响分析...",
    "importance": 4,
    "source": "来源名称",
    "url": "原始链接"
  }}
]

今日新闻条目：
---
{news_items}
---""",
    Category.AI_GITHUB: """你是一位 AI 开源生态分析师。以下是今日 GitHub 上 AI 相关项目的 star 飙升榜和当前排名数据。

任务：
1. 去重合并：将同一项目在不同数据源中的条目合并
2. 项目简介：为每个项目写 1-2 句简介，说明它做什么、解决什么问题，技术关键词保留英文（如 Transformer、LLM、RAG、Diffusion、RLHF 等）
3. 推荐理由：1 句话分析为什么这个项目值得关注或 star 增长快
4. 重要性评级：1-5 星（5 = 现象级项目/可能改变生态，3 = 值得尝试，1 = 一般关注）

输出严格 JSON 数组，不要任何额外文本、markdown 代码块或解释：
[
  {{
    "title": "项目名（保留英文原名）",
    "summary": "项目简介...",
    "impact": "推荐理由...",
    "importance": 4,
    "source": "来源名称",
    "url": "原始链接"
  }}
]

今日项目数据：
---
{news_items}
---""",
}


def _format_news_items(items: list[RawItem], max_items: int = 20) -> str:
    """将原始新闻条目格式化为 prompt 中的文本"""

    lines: list[str] = []
    for i, item in enumerate(items[:max_items], 1):
        summary = item.summary[:200] + "..." if len(item.summary) > 200 else item.summary
        lines.append(
            f"{i}. [{item.source_name}] {item.title}\n   链接: {item.url}\n   摘要: {summary}"
        )

    return "\n\n".join(lines)


def _parse_json_response(response_text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的 JSON，容错处理"""

    text = response_text.strip()

    # 去除可能的 markdown 代码块包裹
    if text.startswith("```"):
        # 去除首行 ```json 或 ```
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
        # 去除末尾 ```
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    # 尝试提取 JSON 数组
    bracket_start = text.find("[")
    bracket_end = text.rfind("]")

    if bracket_start == -1 or bracket_end == -1:
        logger.warning("LLM 响应中未找到 JSON 数组")
        return []

    json_str = text[bracket_start : bracket_end + 1]

    try:
        result = json.loads(json_str)
        if isinstance(result, list):
            return result
        logger.warning("LLM 响应 JSON 不是数组")
        return []
    except json.JSONDecodeError as exc:
        logger.warning("JSON 解析失败: %s", exc)
        # 尝试修复常见的 JSON 错误（如尾逗号）
        fixed = re.sub(r",\s*]", "]", json_str)
        fixed = re.sub(r",\s*}", "}", fixed)
        try:
            result = json.loads(fixed)
            if isinstance(result, list):
                logger.info("JSON 修复成功")
                return result
        except json.JSONDecodeError:
            pass

        logger.warning("JSON 修复失败，返回空列表")
        return []


def _raw_items_to_fallback(items: list[RawItem]) -> list[NewsItem]:
    """LLM 不可用时的降级：直接使用原始摘要"""

    return [
        NewsItem(
            title=item.title,
            summary=item.summary[:150] + "..." if len(item.summary) > 150 else item.summary or "暂无摘要",
            impact="暂无影响分析（LLM 不可用）",
            importance=3,  # 降级时默认 3 星
            source=item.source_name,
            url=item.url,
        )
        for item in items[: settings.max_items_per_category]
    ]


def process_category(
    category: Category,
    items: list[RawItem],
) -> ProcessedCategory:
    """处理单个方向的新闻：LLM 摘要 + 影响分析

    如果新闻条数超过 llm_batch_size，分批处理后合并。
    """

    label = CATEGORY_LABELS[category]

    if not items:
        logger.info("[%s] 无数据，跳过", label)
        return ProcessedCategory(label=label, items=[])

    logger.info("[%s] 处理 %d 条原始新闻...", label, len(items))

    # 如果条数超过 batch_size，分批处理
    batch_size = settings.llm_batch_size
    all_parsed: list[dict[str, Any]] = []

    if len(items) <= batch_size:
        batches = [items]
    else:
        batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
        logger.info("[%s] 分 %d 批处理", label, len(batches))

    for batch_idx, batch in enumerate(batches):
        news_text = _format_news_items(batch, max_items=batch_size)
        prompt = PROMPT_TEMPLATES[category].format(news_items=news_text)

        # 调用 LLM（大批量需要更多输出 token）
        client = get_llm_client()
        max_tokens = min(8192, len(batch) * 300)
        response = client.chat(prompt, max_tokens=max_tokens)

        if not response:
            logger.warning("[%s] 第 %d 批 LLM 无响应", label, batch_idx + 1)
            continue

        # 解析 JSON
        parsed = _parse_json_response(response)

        if not parsed:
            logger.warning("[%s] 第 %d 批 JSON 解析失败", label, batch_idx + 1)
            # 降级：本批使用原始摘要
            fallback = [
                {
                    "title": item.title,
                    "summary": item.summary[:150] + "..." if len(item.summary) > 150 else item.summary or "暂无摘要",
                    "impact": "暂无影响分析",
                    "importance": 3,
                    "source": item.source_name,
                    "url": item.url,
                }
                for item in batch[: settings.max_items_per_category]
            ]
            all_parsed.extend(fallback)
        else:
            all_parsed.extend(parsed)

    if not all_parsed:
        logger.warning("[%s] 全部批次处理失败，降级为原始摘要", label)
        fallback_items = _raw_items_to_fallback(items)
        return ProcessedCategory(label=label, items=fallback_items)

    # 转换为 NewsItem 列表
    news_items: list[NewsItem] = []
    for entry in all_parsed:
        try:
            importance = int(entry.get("importance", 3))
            importance = max(1, min(5, importance))

            news_items.append(
                NewsItem(
                    title=str(entry.get("title", "")).strip(),
                    summary=str(entry.get("summary", "")).strip(),
                    impact=str(entry.get("impact", "")).strip(),
                    importance=importance,
                    source=str(entry.get("source", "")).strip(),
                    url=str(entry.get("url", "")).strip(),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("跳过无效条目: %s", exc)
            continue

    # 按重要性降序排列
    news_items.sort(key=lambda x: x.importance, reverse=True)

    # 保留 Top N
    news_items = news_items[: settings.max_items_per_category]

    logger.info("[%s] 处理完成: %d 条新闻", label, len(news_items))
    return ProcessedCategory(label=label, items=news_items)


def process_all(
    data: dict[Category, list[RawItem]],
) -> dict[Category, ProcessedCategory]:
    """处理所有方向的新闻"""

    results: dict[Category, ProcessedCategory] = {}
    for category, items in data.items():
        results[category] = process_category(category, items)

    return results
