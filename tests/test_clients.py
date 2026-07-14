from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import codex8.core.clients.embeddings as emb_mod
import codex8.core.clients.openai_client as oc


def _fake_openai(monkeypatch, module, **attrs):
    fake = SimpleNamespace(**attrs)
    monkeypatch.setattr(module, "_get_client", lambda: fake, raising=False)
    monkeypatch.setattr(module, "client", lambda: fake, raising=False)
    return fake


async def test_embed_text_uses_configured_model_and_dim(monkeypatch, fake_embedding):
    create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=fake_embedding)])
    )
    _fake_openai(monkeypatch, emb_mod, embeddings=SimpleNamespace(create=create))
    vec = await emb_mod.embed_text("hello")
    assert len(vec) == 1536
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["dimensions"] == 1536


async def test_client_points_at_openai_not_gateway(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from codex8.core.config import get_settings

    get_settings.cache_clear()
    c = oc.client()
    assert "openai" in str(c.base_url)  # default https://api.openai.com/v1 — no gateway
