"""GLM-5.1 API 调用封装：基于 Anthropic SDK 兼容格式"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from anthropic import Anthropic, APIError, APITimeoutError

from src.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端封装，带重试和降级逻辑"""

    def __init__(self) -> None:
        self._client = Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
        )
        self._model = settings.anthropic_model
        self._timeout = settings.llm_timeout
        self._max_retries = settings.llm_max_retries

    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        """发送 prompt 并返回文本响应，带重试逻辑"""

        for attempt in range(1, self._max_retries + 1):
            try:
                start = time.monotonic()
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=self._timeout,
                )
                elapsed = time.monotonic() - start

                # 提取文本内容
                text = ""
                for block in response.content:
                    if block.type == "text":
                        text += block.text

                logger.info(
                    "LLM 响应完成: %d tokens, 耗时 %.1fs (尝试 %d/%d)",
                    len(text),
                    elapsed,
                    attempt,
                    self._max_retries,
                )
                return text

            except APITimeoutError:
                logger.warning("LLM 超时 (尝试 %d/%d)", attempt, self._max_retries)
            except APIError as exc:
                logger.warning(
                    "LLM API 错误 (尝试 %d/%d): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "LLM 未知错误 (尝试 %d/%d): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )

            if attempt < self._max_retries:
                wait = min(2**attempt, 10)  # 指数退避，最多 10 秒
                logger.info("等待 %.1fs 后重试...", wait)
                time.sleep(wait)

        logger.error("LLM 全部重试失败")
        return ""


# 全局单例
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
