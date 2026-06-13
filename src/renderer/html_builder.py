"""HTML 页面生成器：Jinja2 渲染 + JSON 数据文件"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.collectors.rss_collector import Category
from src.config import settings
from src.processor.summarizer import NewsItem, ProcessedCategory

logger = logging.getLogger(__name__)

# Jinja2 模板环境
_template_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
)


def _news_item_to_dict(item: NewsItem) -> dict[str, Any]:
    """将 NewsItem 转为模板可用的字典"""

    return {
        "title": item.title,
        "summary": item.summary,
        "impact": item.impact,
        "importance": item.importance,
        "source": item.source,
        "url": item.url,
    }


def _processed_to_template_data(
    data: dict[Category, ProcessedCategory],
) -> dict[str, Any]:
    """将处理后的数据转为模板渲染所需的格式"""

    categories: dict[str, Any] = {}
    for category, processed in data.items():
        categories[category.value] = {
            "label": processed.label,
            "entries": [_news_item_to_dict(item) for item in processed.items],
        }

    return {"categories": categories}


def render_daily_page(
    target_date: date,
    data: dict[Category, ProcessedCategory],
) -> None:
    """渲染当日首页和归档页面"""

    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # 模板数据
    template_data = _processed_to_template_data(data)
    template_data["date"] = f"{target_date.year}年{target_date.month}月{target_date.day}日"

    # 渲染首页
    template = _template_env.get_template("base.html")
    html = template.render(**template_data)

    index_path = output_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    logger.info("首页已生成: %s", index_path)

    # 渲染归档页面（按日期）
    archive_dir = output_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"{target_date.isoformat()}.html"
    archive_path.write_text(html, encoding="utf-8")
    logger.info("归档页面已生成: %s", archive_path)

    # 保存 JSON 数据文件
    json_data = {
        "date": target_date.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "categories": template_data["categories"],
    }

    json_path = output_dir / f"data/{target_date.isoformat()}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON 数据已生成: %s", json_path)

    # 更新 latest.json（始终指向最新）
    latest_path = output_dir / "data/latest.json"
    latest_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 更新归档索引页
    _update_archive_index(archive_dir)


def _update_archive_index(archive_dir: Path) -> None:
    """更新归档索引页（列出所有历史日报）"""

    # 扫描已有的归档 HTML 文件
    archive_entries: list[dict[str, Any]] = []
    for html_file in sorted(archive_dir.glob("????-??-??.html"), reverse=True):
        # 从文件名提取日期
        date_str = html_file.stem
        try:
            d = date.fromisoformat(date_str)
            display_date = f"{d.year}年{d.month}月{d.day}日"

            # 尝试读取对应的 JSON 获取条目数
            json_path = archive_dir.parent / f"data/{date_str}.json"
            count = 0
            if json_path.exists():
                try:
                    json_data = json.loads(json_path.read_text(encoding="utf-8"))
                    count = sum(
                        len(cat_data.get("entries", []))
                        for cat_data in json_data.get("categories", {}).values()
                    )
                except (json.JSONDecodeError, KeyError):
                    pass

            archive_entries.append(
                {
                    "date": display_date,
                    "filename": html_file.name,
                    "count": count,
                }
            )
        except ValueError:
            continue

    template = _template_env.get_template("archive.html")
    html = template.render(archive_entries=archive_entries)

    index_path = archive_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    logger.info("归档索引页已更新: %d 条记录", len(archive_entries))
