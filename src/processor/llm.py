"""LLM API 调用封装：基于 Anthropic Messages API（token-plan 网关）"""

from __future__ import annotations

import logging
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端封装，带重试和降级逻辑（走 token-plan 网关）"""

    def __init__(self) -> None:
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._client = httpx.Client(timeout=settings.llm_timeout)
        self._max_retries = settings.llm_max_retries

    def chat(self, prompt: str, max_tokens: int = 8192) -> str:
        """发送 prompt 并返回文本响应，带重试逻辑"""

        url = f"{self._base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        for attempt in range(1, self._max_retries + 1):
            try:
                start = time.monotonic()
                resp = self._client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                elapsed = time.monotonic() - start

                # Anthropic 响应 content 是数组（可能含 thinking/text 等块），只提取 text 块
                text = "".join(
                    block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                )

                logger.info(
                    "LLM 响应完成: %d 字符, 耗时 %.1fs (尝试 %d/%d)",
                    len(text),
                    elapsed,
                    attempt,
                    self._max_retries,
                )
                return text

            except httpx.TimeoutException:
                logger.warning("LLM 超时 (尝试 %d/%d)", attempt, self._max_retries)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "LLM API 错误 (尝试 %d/%d): HTTP %d %s",
                    attempt,
                    self._max_retries,
                    exc.response.status_code,
                    exc.response.text[:300],
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