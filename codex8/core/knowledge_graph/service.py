"""KG read helpers — the read side of the populated graph.

kb_id ──► read_graph (full / focus-BFS)   kg_stats (counts)   kg_schema (ontology)
"""

from __future__ import annotations

from codex8.store import Store

_DIGEST_NODE_CAP = 5000
_DIGEST_EDGE_CAP = 5000


def _shape_nodes(rows: list) -> list[dict]:
    """Surface entity-resolution fields on read."""
    shaped: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        n = dict(r)
        n["aliases"] = list(n.get("aliases") or [])
        n["merge_count"] = len(n.pop("merge_history", None) or [])
        shaped.append(n)
    return shaped


def read_graph(
    store: Store,
    kb_id: str,
    *,
    focus: str | None = None,
    depth: int = 2,
    node_cap: int = 500,
    edge_cap: int = 2000,
) -> dict:
    """Full graph (capped) or a depth-bounded BFS subgraph around `focus`."""
    if not focus:
        graph = store.get_kg_subgraph(kb_id, node_cap=node_cap, edge_cap=edge_cap)
        return {"nodes": _shape_nodes(graph.get("nodes") or []), "edges": graph.get("edges") or []}
    needle = focus.strip().lower()
    seed_ids = [
        n["id"]
        for n in store.list_kg_nodes(kb_id, limit=node_cap)
        if isinstance(n, dict) and needle in str(n.get("label", "")).lower()
    ][:10]
    if not seed_ids:
        return {"nodes": [], "edges": []}
    graph = store.get_kg_subgraph(
        kb_id, seed_node_ids=seed_ids, node_cap=node_cap, edge_cap=edge_cap, depth=depth
    )
    return {"nodes": _shape_nodes(graph.get("nodes") or []), "edges": graph.get("edges") or []}


def kg_stats(store: Store, kb_id: str) -> dict:
    """Node/edge totals + counts by node type and by relation."""
    return store.kg_stats(kb_id)


def kg_schema(store: Store, kb_id: str) -> dict:
    """The ontology actually present in the KG: distinct node types + relations."""
    stats = store.kg_stats(kb_id)
    return {
        "node_types": sorted(stats["by_type"].keys()),
        "relations": sorted(stats["by_relation"].keys()),
        "node_count": stats["node_count"],
        "edge_count": stats["edge_count"],
    }


def get_kg_intent(store: Store, kb_id: str) -> dict | None:
    """The KB's highest-version approved KG intent schema, or None if never set."""
    row = store.get_kg_intent(kb_id)
    if not row:
        return None
    schema = row.get("schema") or {}
    if isinstance(schema, dict):
        return {**schema, "version": row.get("version", schema.get("version", 1))}
    return None


def set_kg_intent(store: Store, kb_id: str, org_id: str, schema: dict) -> dict:
    """Persist an approved schema as the next version (never overwrites history)."""
    row = store.set_kg_intent(org_id, kb_id, schema)
    return {**schema, "version": row.get("version", 1)}


def kg_schema_view(store: Store, kb_id: str) -> dict:
    """Both approved and emergent ontologies for the KB."""
    return {"intent": get_kg_intent(store, kb_id), "emergent": kg_schema(store, kb_id)}


def kg_digest(store: Store, kb_ids: list[str], *, top_n: int = 8) -> dict:
    """Top entities (by edge degree) + top relations (by frequency) across KBs."""
    if not kb_ids:
        return {"node_count": 0, "edge_count": 0, "top_entities": [], "top_relations": []}
    nodes: list[dict] = []
    edges: list[dict] = []
    for kb_id in kb_ids:
        graph = store.get_kg_subgraph(kb_id, node_cap=_DIGEST_NODE_CAP, edge_cap=_DIGEST_EDGE_CAP)
        nodes.extend(graph.get("nodes") or [])
        edges.extend(graph.get("edges") or [])
    by_id = {str(r["id"]): r for r in nodes if isinstance(r, dict) and r.get("id")}
    degree: dict[str, int] = {}
    rel_count: dict[str, int] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        for endpoint in (e.get("source_node_id"), e.get("target_node_id")):
            if endpoint:
                key = str(endpoint)
                degree[key] = degree.get(key, 0) + 1
        rel = str(e.get("relation") or "unknown")
        rel_count[rel] = rel_count.get(rel, 0) + 1
    ranked = sorted(
        by_id.items(),
        key=lambda kv: (degree.get(kv[0], 0), str(kv[1].get("label", ""))),
        reverse=True,
    )
    top_entities = [
        {
            "label": str(n.get("label", "")),
            "type": str(n.get("type", "")),
            "degree": degree.get(node_id, 0),
        }
        for node_id, n in ranked[:top_n]
    ]
    top_relations = [
        {"relation": rel, "count": cnt}
        for rel, cnt in sorted(rel_count.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[
            :top_n
        ]
    ]
    return {
        "node_count": len(by_id),
        "edge_count": len(edges),
        "top_entities": top_entities,
        "top_relations": top_relations,
    }


def focus_subgraph(nodes: list[dict], edges: list[dict], *, max_nodes: int = 20) -> dict:
    """Top-degree induced subgraph — pure (no Store)."""
    if not nodes:
        return {"nodes": [], "edges": []}
    degree: dict[str, int] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        for endpoint in (e.get("source_node_id"), e.get("target_node_id")):
            if endpoint:
                key = str(endpoint)
                degree[key] = degree.get(key, 0) + 1
    ranked = sorted(
        (n for n in nodes if isinstance(n, dict) and n.get("id")),
        key=lambda n: (degree.get(str(n["id"]), 0), str(n.get("label", "")) or str(n["id"])),
        reverse=True,
    )
    kept = ranked[:max_nodes]
    kept_ids = {str(n["id"]) for n in kept}
    induced = [
        e
        for e in edges
        if isinstance(e, dict)
        and str(e.get("source_node_id")) in kept_ids
        and str(e.get("target_node_id")) in kept_ids
    ]
    return {"nodes": kept, "edges": induced}


def kg_focus_subgraph(store: Store, kb_id: str, *, max_nodes: int = 20) -> dict:
    """Fetch the KB's graph and reduce it to a legible top-degree subgraph."""
    graph = read_graph(store, kb_id)
    return focus_subgraph(graph.get("nodes") or [], graph.get("edges") or [], max_nodes=max_nodes)


def render_kg_context(digest: dict) -> str:
    """Render a `kg_digest` as a tight written block for the conversation."""
    n, m = digest.get("node_count", 0), digest.get("edge_count", 0)
    if not n:
        return "Knowledge graph: not built yet — run `codex8_build_graph` to populate it."
    lines = [f"Knowledge graph: {n} entities, {m} relations."]
    ents = digest.get("top_entities") or []
    if ents:
        lines.append(
            "Most connected: "
            + ", ".join(
                f"{e['label']} ({e['degree']})" if e.get("degree") else str(e["label"])
                for e in ents
            )
            + "."
        )
    rels = digest.get("top_relations") or []
    if rels:
        lines.append(
            "Key relations: " + ", ".join(f"{r['relation']} ×{r['count']}" for r in rels) + "."
        )
    return "\n".join(lines)
