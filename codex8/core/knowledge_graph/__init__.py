"""Knowledge-graph build: findings → entities/relations → kg_nodes/kg_edges.

    findings ─► extractor (LLM) ─► KGExtraction ─► builder (dedupe + upsert) ─► KG

The write side of the already-shipped `/v1/graph` + `codex8_graph` reads.
Pure extraction/resolution logic lives here; Store persistence is in builder.
"""
