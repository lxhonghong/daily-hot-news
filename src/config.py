"""项目配置：从环境变量加载所有配置项"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录
PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置，从 .env 文件和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== LLM API 配置 =====
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://www.huolilink.com"
    anthropic_model: str = "GLM-5.1"

    # ===== CurrentsAPI 配置 =====
    currents_api_key: str = ""

    # ===== RSSHub 配置 =====
    rsshub_base_url: str = "http://localhost:1200"

    # ===== 知乎 Cookie =====
    zhihu_cookies: str = ""

    # ===== HTTP 代理配置（用于访问国际源）=====
    http_proxy: str = "http://127.0.0.1:54771"
    https_proxy: str = "http://127.0.0.1:54771"

    # ===== Git 配置 =====
    git_repo_dir: str = str(PROJECT_DIR)

    # ===== 通知配置 =====
    enable_macos_notification: bool = True

    # ===== 输出目录 =====
    output_dir: Path = PROJECT_DIR / "output"
    data_dir: Path = PROJECT_DIR / "data" / "raw"
    logs_dir: Path = PROJECT_DIR / "logs"

    # ===== 采集参数 =====
    # 每个 RSS feed 的超时时间（秒）
    rss_timeout: float = 15.0
    # 每个 CurrentsAPI 请求的超时时间（秒）
    currents_timeout: float = 15.0
    # 并发采集最大数
    max_concurrent: int = 10
    # 每方向保留的最大条目数
    max_items_per_category: int = 15

    # ===== LLM 参数 =====
    # LLM 请求超时（秒）
    llm_timeout: float = 60.0
    # LLM 重试次数
    llm_max_retries: int = 3
    # 每批发给 LLM 的最大新闻条数
    llm_batch_size: int = 20


# 全局单例
settings = Settings()
