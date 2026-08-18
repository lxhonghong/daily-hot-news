"""llm.py 单元测试：验证 Anthropic Messages API 的请求构造与响应解析"""

from __future__ import annotations

import pytest

from src.processor import llm as llm_module


class FakeResponse:
    """模拟 httpx.Response：只实现代码中用到的方法"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """记录请求参数并返回固定响应的假 httpx.Client"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.posted: tuple | None = None

    def post(self, url: str, headers: dict | None = None, json: dict | None = None):
        self.posted = (url, headers, json)
        return FakeResponse(self._payload)


def _make_payload(text: str = "这是摘要", with_thinking: bool = True) -> dict:
    content = [{"type": "text", "text": text}]
    if with_thinking:
        content.insert(0, {"type": "thinking", "thinking": "思考过程", "signature": "sig"})
    return {"id": "msg_1", "type": "message", "role": "assistant", "content": content, "usage": {}}


@pytest.fixture
def fake(monkeypatch):
    """让 LLMClient 使用假 client，并固定 settings 值"""

    def _install(payload: dict) -> FakeClient:
        client = FakeClient(payload)
        monkeypatch.setattr(llm_module.httpx, "Client", lambda **kw: client)
        monkeypatch.setattr(llm_module.settings, "llm_base_url", "https://gw.test/anthropic")
        monkeypatch.setattr(llm_module.settings, "llm_api_key", "sk-test")
        monkeypatch.setattr(llm_module.settings, "llm_model", "deepseek-v4-flash-0731")
        return client

    return _install


def test_chat_builds_correct_request(fake) -> None:
    """当缺少 API 密钥时……构造的请求应使用 Bearer 认证与正确模型名"""
    client = fake(_make_payload())
    out = llm_module.LLMClient().chat("prompt内容", max_tokens=64)

    assert out == "这是摘要"
    url, headers, body = client.posted
    assert url == "https://gw.test/anthropic/v1/messages"
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["model"] == "deepseek-v4-flash-0731"
    assert body["max_tokens"] == 64
    assert body["messages"] == [{"role": "user", "content": "prompt内容"}]


def test_chat_skips_thinking_block_and_concats_text(fake) -> None:
    """响应 content 含 thinking 块时，只提取 text 块并拼接"""
    client = fake(_make_payload(text="第一句", with_thinking=True))
    out = llm_module.LLMClient().chat("x")
    assert out == "第一句"


def test_chat_on_http_error_returns_empty(monkeypatch) -> None:
    """HTTP 错误且重试耗尽后应返回空字符串（触发 summarizer 降级）"""

    class BadResponse:
        status_code = 500
        text = "Internal Server Error"  # httpx.Response 的 .text 属性

        def raise_for_status(self) -> None:
            raise llm_module.httpx.HTTPStatusError(
                "500", request=llm_module.httpx.Request("POST", "http://x"), response=self
            )

    class BadClient:
        def post(self, *args, **kwargs):
            return BadResponse()

    monkeypatch.setattr(llm_module.httpx, "Client", lambda **kw: BadClient())
    monkeypatch.setattr(llm_module.settings, "llm_base_url", "https://gw.test/anthropic")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(llm_module.settings, "llm_model", "deepseek-v4-flash-0731")
    # 只重试 2 次，避免测试耗时
    monkeypatch.setattr(llm_module.settings, "llm_max_retries", 2)

    out = llm_module.LLMClient().chat("x")
    assert out == ""