"""主入口：串联 采集 → 去重 → LLM 摘要 → 渲染 → 推送 全流程"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from src.collectors.rss_collector import Category, collect_all_feeds
from src.collectors.currents import collect_currents
from src.config import settings
from src.processor.deduper import deduplicate_all
from src.processor.summarizer import process_all
from src.renderer.html_builder import render_daily_page

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """配置日志"""

    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    log_file = logs_dir / f"{today}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )


def notify_macos(title: str, message: str) -> None:
    """弹 macOS 通知"""

    if not settings.enable_macos_notification:
        return

    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            check=False,
            timeout=5,
        )
    except Exception:
        logger.debug("macOS 通知失败，忽略")


async def run_pipeline() -> bool:
    """执行完整的采集→处理→渲染→推送流水线

    返回 True 表示成功，False 表示失败
    """

    today = date.today()
    logger.info("=" * 60)
    logger.info("每日热点速递 | %s", today.isoformat())
    logger.info("=" * 60)

    try:
        # ===== Phase 1: 采集 =====
        logger.info("[Phase 1] 采集开始...")
        rss_results = await collect_all_feeds()
        currents_results = await collect_currents()

        # 合并 RSS 和 CurrentsAPI 数据
        combined: dict[Category, list] = {
            Category.AI_TECH: rss_results[Category.AI_TECH] + currents_results[Category.AI_TECH],
            Category.INTERNATIONAL: rss_results[Category.INTERNATIONAL]
            + currents_results[Category.INTERNATIONAL],
            Category.DOMESTIC: rss_results[Category.DOMESTIC] + currents_results[Category.DOMESTIC],
        }

        total_raw = sum(len(v) for v in combined.values())
        logger.info("[Phase 1] 采集完成: 共 %d 条原始数据", total_raw)

        if total_raw == 0:
            logger.error("所有数据源均采集失败，无法生成日报")
            return False

        # ===== Phase 2: 去重 + LLM 处理 =====
        logger.info("[Phase 2] 去重 + LLM 处理...")
        deduped = deduplicate_all(combined)
        processed = process_all(deduped)

        total_processed = sum(len(v.items) for v in processed.values())
        logger.info("[Phase 2] 处理完成: 共 %d 条新闻", total_processed)

        # ===== Phase 3: 渲染 =====
        logger.info("[Phase 3] 渲染 HTML...")
        render_daily_page(today, processed)
        logger.info("[Phase 3] 渲染完成")

        # ===== Phase 4: Git 推送 =====
        logger.info("[Phase 4] 推送到 Git...")
        success = git_push(today)
        if success:
            logger.info("[Phase 4] 推送成功")
        else:
            logger.warning("[Phase 4] 推送失败，但日报已生成本地")

        logger.info("=" * 60)
        logger.info("每日热点速递完成!")
        logger.info("=" * 60)
        return True

    except Exception as exc:
        logger.exception("流水线异常: %s", exc)
        return False


def git_push(target_date: date) -> bool:
    """将生成的文件 commit 并 push 到远程仓库"""

    try:
        repo_dir = Path(settings.git_repo_dir)

        # git add
        subprocess.run(
            ["git", "add", "output/"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            timeout=30,
        )

        # 检查是否有变更
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(repo_dir),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info("无变更，跳过推送")
            return True

        # git commit
        subprocess.run(
            ["git", "commit", "-m", f"daily: {target_date.isoformat()}"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            timeout=30,
        )

        # git push
        subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            timeout=60,
        )

        return True

    except subprocess.TimeoutExpired:
        logger.error("Git 操作超时")
        return False
    except subprocess.CalledProcessError as exc:
        logger.error("Git 操作失败: %s", exc.stderr.decode() if exc.stderr else exc)
        return False
    except Exception as exc:
        logger.error("Git 推送异常: %s", exc)
        return False


def main() -> None:
    """主入口函数"""

    setup_logging()
    logger.info("启动每日热点速递...")

    success = asyncio.run(run_pipeline())

    if success:
        logger.info("✅ 全流程成功完成")
    else:
        logger.error("❌ 全流程失败")
        notify_macos("每日热点速递", "⚠️ 日报生成失败，请检查日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
