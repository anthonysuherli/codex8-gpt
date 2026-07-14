from __future__ import annotations

from codex8.store import get_store
from codex8.store.sqlite import SQLiteStore


def _kb(s: SQLiteStore) -> str:
    org_id, project_id = s.resolve_project("p1", create=True)
    return s.resolve_kb(org_id, project_id, "kb1", create=True)


async def test_insert_then_match_roundtrip(tmp_path, fake_embedding, fake_embedding_other):
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = _kb(s)
    rows = [
        {"kb_id": kb_id, "title": "near", "content": "near finding", "embedding": fake_embedding},
        {
            "kb_id": kb_id,
            "title": "far",
            "content": "far finding",
            "embedding": fake_embedding_other,
        },
    ]
    ids = await s.insert_findings(rows)
    assert len(ids) == 2
    hits = await s.match_findings(kb_id, fake_embedding, match_count=1, min_similarity=0.0)
    assert hits[0]["title"] == "near"
    assert hits[0]["similarity"] > 0.99


def test_get_store_is_always_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "env.db"))
    assert isinstance(get_store(), SQLiteStore)
