"""Unit tests for the OpenAI-compatible provider (mocked HTTP)."""
import json

import httpx
import pytest

from app.config import Settings
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.provider import LLMError


def make_provider(**overrides) -> OpenAICompatibleProvider:
    kwargs = dict(
        llm_base_url="http://llm.test/v1",
        llm_model="qwen-test",
        llm_api_key="secret-key",
        llm_timeout_seconds=5,
        llm_max_tokens=100,
    )
    kwargs.update(overrides)
    settings = Settings(**kwargs)
    import app.llm.openai_compatible as mod
    mod.get_settings = lambda: settings
    provider = OpenAICompatibleProvider()
    return provider


def _ok_response(content: str = '{"title": "t"}') -> httpx.Response:
    body = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "http://llm.test/v1/chat/completions"))


def test_success(monkeypatch):
    provider = make_provider()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _ok_response()

    monkeypatch.setattr(httpx, "post", fake_post)
    result = provider.complete("sys", "user")
    assert result == '{"title": "t"}'
    assert captured["url"] == "http://llm.test/v1/chat/completions"
    assert captured["json"]["model"] == "qwen-test"
    assert captured["json"]["temperature"] == 0
    assert captured["json"]["max_tokens"] == 100
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["timeout"] == 5


def test_no_api_key_no_auth_header(monkeypatch):
    provider = make_provider(llm_api_key="")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _ok_response()

    monkeypatch.setattr(httpx, "post", fake_post)
    provider.complete("sys", "user")
    assert "Authorization" not in captured["headers"]


def test_401(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(401, text="unauthorized", request=httpx.Request("POST", "x")),
    )
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "401" in str(exc.value)
    assert "secret-key" not in str(exc.value)


def test_429(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(429, text="rate limited", request=httpx.Request("POST", "x")),
    )
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "429" in str(exc.value)


def test_5xx_includes_snippet(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(500, text="internal boom " + "y" * 400, request=httpx.Request("POST", "x")),
    )
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    msg = str(exc.value)
    assert "500" in msg
    assert "internal boom" in msg
    assert len(msg) < 500  # snippet truncated


def test_timeout(monkeypatch):
    provider = make_provider()

    def fake_post(*a, **k):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "timed out" in str(exc.value).lower() or "timeout" in str(exc.value).lower()


def test_connection_error(monkeypatch):
    provider = make_provider()

    def fake_post(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "Could not reach" in str(exc.value)


def test_non_json_response(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, text="<html>not json</html>", request=httpx.Request("POST", "x")),
    )
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "non-JSON" in str(exc.value)


def test_empty_content(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _ok_response(content="   "))
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "empty" in str(exc.value).lower()


def test_missing_choices(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, json={"error": "nope"}, request=httpx.Request("POST", "x")),
    )
    with pytest.raises(LLMError) as exc:
        provider.complete("sys", "user")
    assert "choices" in str(exc.value)
