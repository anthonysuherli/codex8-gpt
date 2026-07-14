from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.core.agent.preamble as preamble_mod
import codex8.mcp.server as server


async def test_resume_returns_contract_keys(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "t.db"))
    # select_preamble embeds through preamble's own module binding — patch there,
    # not on the server module (server.embed_text only feeds codex8_search).
    monkeypatch.setattr(preamble_mod, "embed_text", AsyncMock(return_value=fake_embedding))
    # resume resolves with create=False (only explore creates on demand) — seed first.
    server.resolve_tenant("p", "k", create=True)
    out = await server.codex8_resume(project="p", kb="k", query="q")
    assert set(out) >= {"banner", "preamble", "coverage"}
    assert out["coverage"] in {"rich", "sparse", "gap"}


async def test_projects_lists_created_kb(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "t.db"))
    server.resolve_tenant("p", "k", create=True)
    out = await server.codex8_resume(project="p", kb="k", query=None)
    assert "error" not in out
    listed = await server.codex8_projects()
    names = [p["project"] for p in listed["projects"]]
    assert "p" in names
