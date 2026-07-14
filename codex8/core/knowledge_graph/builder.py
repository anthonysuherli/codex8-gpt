"""KG builder — gather findings, extract a graph, dedupe + persist.

findings ─► extract_graph ─► collapse nodes ─► upsert_kg_nodes ─► kg_nodes
                                          └─► resolve edge labels → ids ─► kg_edges
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from codex8.core.clients.embeddings import embed_batch
from codex8.core.config import get_config
from codex8.core.knowledge_graph import service as kg_service
from codex8.core.knowledge_graph.extractor import extract_graph
from codex8.core.knowledge_graph.models import KGEdgeExtract, KGNodeExtract
from codex8.core.knowledge_graph.schema import KGSchema
from codex8.store import Store, get_store

if TYPE_CHECKING:
    from codex8.core.agent.state import TenantContext

logger = logging.getLogger(__name__)


def _norm(label: str) -> str:
    """Normalize a label for exact in-batch matching: trim, lower, collapse ws."""
    return " ".join(label.strip().lower().split())


def _collapse_nodes(nodes: list[KGNodeExtract]) -> list[KGNodeExtract]:
    """Merge extracted nodes sharing a normalized label (first-seen order)."""
    merged: dict[str, KGNodeExtract] = {}
    for n in nodes:
        key = _norm(n.label)
        if not key:
            continue
        if key in merged:
            existing = merged[key]
            props = {**n.properties, **existing.properties}
            grounded = list(dict.fromkeys([*existing.grounded_in, *n.grounded_in]))
            aliases = list(
                dict.fromkeys(
                    a for a in [*existing.aliases, n.label, *n.aliases] if a and a != existing.label
                )
            )
            merged[key] = existing.model_copy(
                update={"properties": props, "grounded_in": grounded, "aliases": aliases}
            )
        else:
            merged[key] = n
    return list(merged.values())


def _resolve_edges(edges: list[KGEdgeExtract], label_to_id: dict[str, str]) -> list[dict]:
    """Map each edge's source/target labels to node ids via `label_to_id`."""
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        sid = label_to_id.get(_norm(e.source))
        tid = label_to_id.get(_norm(e.target))
        if not sid or not tid or sid == tid:
            continue
        key = (sid, tid, e.relation)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_node_id": sid,
                "target_node_id": tid,
                "relation": e.relation,
                "properties": e.properties,
                "grounded_in": e.grounded_in,
            }
        )
    return out


def _load_intent(store: Store, kb_id: str) -> KGSchema | None:
    """Read the KB's highest-version intent schema, if any."""
    raw = kg_service.get_kg_intent(store, kb_id)
    if not raw:
        return None
    try:
        return KGSchema.model_validate(raw)
    except Exception:  # noqa: BLE001 — a bad stored schema must not sink the build
        logger.warning("KB %s has a malformed KG intent schema; building free-form", kb_id)
        return None


def _gather_findings(
    store: Store, kb_id: str, *, finding_ids: list[str] | None, max_findings: int
) -> list[dict]:
    """Load findings (with content) for extraction."""
    if finding_ids:
        ids = finding_ids
    else:
        listing = store.list_findings(kb_id, limit=max_findings)
        rows = listing.get("findings", []) if isinstance(listing, dict) else []
        ids = [r["id"] for r in rows if isinstance(r, dict) and r.get("id")]
    findings: list[dict] = []
    for fid in ids:
        try:
            findings.append(store.get_finding(kb_id, fid))
        except Exception:  # noqa: BLE001 — a stale/absent id just drops from the delta
            logger.debug("KG build: finding %s not found in kb=%s", fid, kb_id)
    return findings


async def build_graph(
    ctx: TenantContext,
    *,
    max_findings: int | None = None,
    rebuild: bool = True,
    use_schema: bool = True,
    finding_ids: list[str] | None = None,
    store: Store | None = None,
) -> dict:
    """Extract entities/relations from the KB's findings and persist them."""
    cfg = get_config().knowledge_graph
    store = store or get_store(
        getattr(ctx, "access_token", None), org_id=getattr(ctx, "org_id", None)
    )
    if finding_ids:
        rebuild = False
    findings = _gather_findings(
        store, ctx.kb_id, finding_ids=finding_ids, max_findings=max_findings or cfg.max_findings
    )
    if not findings:
        return {
            "findings_scanned": 0,
            "nodes_created": 0,
            "edges_created": 0,
            "node_count": 0,
            "edge_count": 0,
        }
    schema = _load_intent(store, ctx.kb_id) if use_schema else None
    extraction = await extract_graph(findings, cfg, schema)
    nodes = _collapse_nodes(extraction.nodes)[: cfg.max_nodes]
    if rebuild:
        store.clear_kg(ctx.kb_id)
    stats_before = store.kg_stats(ctx.kb_id)
    label_to_id: dict[str, str] = {}
    if nodes:
        embeddings = await embed_batch([nd.label for nd in nodes])
        node_rows = [
            {
                "type": nd.type,
                "label": nd.label,
                "properties": nd.properties,
                "grounded_in": nd.grounded_in,
                "embedding": emb,
            }
            for nd, emb in zip(nodes, embeddings)
        ]
        ids = await store.upsert_kg_nodes(ctx.kb_id, node_rows)
        for nd, nid in zip(nodes, ids):
            label_to_id[_norm(nd.label)] = nid
    edges = _resolve_edges(extraction.edges, label_to_id)[: cfg.max_edges]
    edges_created = await store.upsert_kg_edges(ctx.kb_id, edges) if edges else 0
    stats_after = store.kg_stats(ctx.kb_id)
    return {
        "findings_scanned": len(findings),
        "nodes_created": max(stats_after["node_count"] - stats_before["node_count"], 0),
        "edges_created": edges_created,
        "node_count": stats_after["node_count"],
        "edge_count": stats_after["edge_count"],
    }


_KG_BG_TASKS: set[asyncio.Task] = set()


async def _auto_kg_update(
    ctx: TenantContext, finding_ids: list[str], *, store: Store | None = None
) -> None:
    """Append freshly-explored findings to the KG when an intent schema exists."""
    try:
        store = store or get_store(
            getattr(ctx, "access_token", None), org_id=getattr(ctx, "org_id", None)
        )
        if not kg_service.get_kg_intent(store, ctx.kb_id):
            return
        result = await build_graph(ctx, finding_ids=finding_ids, use_schema=True, store=store)
        logger.info(
            "auto KG update kb=%s: +%s nodes, +%s edges (%s findings)",
            ctx.kb_id,
            result.get("nodes_created"),
            result.get("edges_created"),
            len(finding_ids),
        )
    except Exception:  # noqa: BLE001 — auto-grow is best-effort, never breaks a turn
        logger.exception("auto KG update failed for kb=%s", ctx.kb_id)


def schedule_kg_update(
    ctx: TenantContext, finding_ids: list[str], *, store: Store | None = None
) -> None:
    """Fire-and-forget incremental KG update that will not be GC'd mid-flight."""
    if not finding_ids:
        return
    task = asyncio.create_task(_auto_kg_update(ctx, finding_ids, store=store))
    _KG_BG_TASKS.add(task)
    task.add_done_callback(_KG_BG_TASKS.discard)
