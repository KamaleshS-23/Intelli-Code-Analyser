from types import SimpleNamespace

import pytest

from ai_assistant import provider


def _settings(**overrides):
    settings = {
        "provider": "groq",
        "code_generation_provider": "gemini",
        "gemini_api_key": "test-key",
        "gemini_model": "gemini-test-model",
        "model": "groq-test-model",
    }
    settings.update(overrides)
    return SimpleNamespace(**settings)


def test_code_generation_provider_uses_separate_gemini_model(monkeypatch):
    created = {}

    class FakeGeminiProvider:
        def __init__(self, model):
            created["model"] = model

    monkeypatch.setattr(provider, "get_ai_settings", lambda: _settings())
    monkeypatch.setattr(provider, "GeminiProvider", FakeGeminiProvider)

    result = provider.get_code_generation_provider()

    assert isinstance(result, FakeGeminiProvider)
    assert created["model"] == "gemini-test-model"


def test_code_generation_provider_leaves_chatbot_provider_unchanged(monkeypatch):
    chat_provider = object()
    code_provider = object()
    monkeypatch.setattr(provider, "get_ai_settings", lambda: _settings())
    monkeypatch.setattr(provider, "get_provider", lambda: chat_provider)
    monkeypatch.setattr(
        provider,
        "GeminiProvider",
        lambda model: code_provider,
    )

    assert provider.get_provider() is chat_provider
    assert provider.get_code_generation_provider() is code_provider


def test_code_generation_provider_requires_gemini_key(monkeypatch):
    monkeypatch.setattr(
        provider,
        "get_ai_settings",
        lambda: _settings(gemini_api_key=""),
    )

    with pytest.raises(RuntimeError, match="Set GEMINI_API_KEY"):
        provider.get_code_generation_provider()


def test_default_code_generation_provider_uses_chat_provider(monkeypatch):
    chat_provider = object()
    monkeypatch.setattr(
        provider,
        "get_ai_settings",
        lambda: _settings(code_generation_provider="default"),
    )
    monkeypatch.setattr(provider, "get_provider", lambda: chat_provider)

    assert provider.get_code_generation_provider() is chat_provider


def test_gemini_provider_rotates_to_second_key_on_rate_limit(monkeypatch):
    import urllib.error

    calls = []

    settings = _settings(
        gemini_keys=(("key-1", "model-1"), ("key-2", "model-2")),
        gemini_api_key="key-1",
    )
    monkeypatch.setattr(provider, "get_ai_settings", lambda: settings)

    gemini_provider = provider.GeminiProvider()

    def fake_call_model(model, api_key, prompt):
        calls.append((model, api_key))
        if api_key == "key-1":
            raise urllib.error.HTTPError("http://example.com", 429, "Too Many Requests", {}, None)
        return "success from key-2"

    monkeypatch.setattr(gemini_provider, "_call_model", fake_call_model)
    result = gemini_provider.generate("test prompt")

    assert result == "success from key-2"
    assert ("model-1", "key-1") in calls
    assert ("model-2", "key-2") in calls
