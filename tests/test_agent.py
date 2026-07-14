from __future__ import annotations

import json
from unittest.mock import AsyncMock

import codex8.core.agent.preamble as preamble_mod
import codex8.core.agent.synopsis as synopsis_mod
from codex8.core.agent.preamble import select_preamble
from codex8.core.agent.state import TenantContext
from codex8.core.agent.synopsis import load_synopsis, maybe_rebuild_synopsis
from codex8.store.sqlite import SQLiteStore


def _kb(store: SQLiteStore) -> str:
    org_id, project_id = store.resolve_project("p", create=True)
    return store.resolve_kb(org_id, project_id, "kb", create=True)


async def test_preamble_coverage_gap_on_empty_kb(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setattr(preamble_mod, "embed_text", AsyncMock(return_value=fake_embedding))
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = _kb(s)
    xml, coverage = await select_preamble("anything", store=s, kb_id=kb_id, depth="normal")
    assert coverage == "gap"
    assert "<preamble>" in xml


def test_tenant_context_shape():
    ctx = TenantContext(
        user_id="local",
        org_id="local",
        project_id="x",
        kb_id="y",
        thread_id="t",
        access_token="",
    )
    assert ctx.org_id == "local"


async def test_synopsis_rebuild_uses_text_completion(tmp_path, monkeypatch, fake_embedding):
    entries = [{"topic": "sqlite", "gloss": "The KB knows about sqlite-vec storage."}]
    fake_llm = AsyncMock(return_value=json.dumps(entries))
    monkeypatch.setattr(synopsis_mod, "text_completion", fake_llm)
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = _kb(s)
    await s.insert_findings(
        [
            {
                "kb_id": kb_id,
                "title": "sqlite-vec",
                "content": "vec0 tables",
                "category": "fact",
                "confidence": 0.9,
                "embedding": fake_embedding,
            }
        ]
    )
    await maybe_rebuild_synopsis(kb_id, store=s)
    fake_llm.assert_awaited_once()
    assert "model" in fake_llm.await_args.kwargs
    row = load_synopsis(s, kb_id)
    assert row is not None
    assert row["content"] == entries
