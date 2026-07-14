from __future__ import annotations

from codex8.core.config import get_config, get_settings


def test_settings_only_openai_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.openai_api_key == "sk-test"
    assert not hasattr(settings, "tavily_api_key")
    assert not hasattr(settings, "ai_gateway_api_key")
    assert not hasattr(settings, "supabase_url")


def test_config_defaults_are_gpt56(monkeypatch):
    monkeypatch.delenv("CODEX8_CONFIG_FILE", raising=False)
    get_config.cache_clear()
    config = get_config()
    assert config.exploration.planner_model == "gpt-5.6-terra"
    assert config.exploration.extraction_fallback_model == "gpt-5.6-luna"
    assert config.synopsis.model == "gpt-5.6-luna"
    assert config.embedding.model == "text-embedding-3-small"
    assert config.embedding.dim == 1536


def test_env_override_uses_c8_prefix(monkeypatch):
    monkeypatch.setenv("C8_TIERS__RICH_HIT_COUNT", "7")
    get_config.cache_clear()
    assert get_config().tiers.rich_hit_count == 7
