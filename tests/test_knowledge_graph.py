from __future__ import annotations

import importlib
import importlib.util

import pytest


def test_kg_package_imports():
    from codex8.core.knowledge_graph.builder import schedule_kg_update
    from codex8.core.knowledge_graph.service import read_graph

    assert callable(schedule_kg_update) and callable(read_graph)


def test_agent_concept_doc_imports_end_to_end():
    # concept_doc (Task 6) imports read_graph from this task's service module —
    # once both packages exist the agent package must import cleanly end-to-end.
    try:
        spec = importlib.util.find_spec("codex8.core.agent.concept_doc")
    except ModuleNotFoundError:
        spec = None
    if spec is None:
        pytest.skip("agent package (Task 6) not landed yet — cross-task import deferred")
    importlib.import_module("codex8.core.agent.concept_doc")


async def test_read_graph_returns_seeded_nodes_and_edges(tmp_path):
    from codex8.core.knowledge_graph.service import read_graph
    from codex8.store.sqlite import SQLiteStore

    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    org_id, project_id = s.resolve_project("p1", create=True)
    kb_id = s.resolve_kb(org_id, project_id, "kb1", create=True)

    ids = await s.upsert_kg_nodes(
        kb_id,
        [
            {"type": "company", "label": "Acme", "properties": {"hq": "Berlin"}, "grounded_in": []},
            {"type": "person", "label": "Ada", "properties": {}, "grounded_in": []},
        ],
    )
    assert len(ids) == 2
    inserted = await s.upsert_kg_edges(
        kb_id,
        [
            {
                "source_node_id": ids[0],
                "target_node_id": ids[1],
                "relation": "founded_by",
                "properties": {},
                "grounded_in": [],
            }
        ],
    )
    assert inserted == 1

    graph = read_graph(s, kb_id)
    assert {n["label"] for n in graph["nodes"]} == {"Acme", "Ada"}
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["source_node_id"] == ids[0]
    assert edge["target_node_id"] == ids[1]
    assert edge["relation"] == "founded_by"
    # Local tier carries no aliases/merge_history columns — the read shape still
    # surfaces the entity-resolution fields, degraded to empty/zero.
    assert all(n["aliases"] == [] and n["merge_count"] == 0 for n in graph["nodes"])
