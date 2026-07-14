"""FastMCP stdio server — the local Codex8 entry path.

    MCP tool call ──► resolve_tenant(project, kb) ──► get_store() ──► engine

The deliberately small surface has four tools: ``codex8_resume``,
``codex8_search``, ``codex8_explore``, and ``codex8_projects``. Run with
``python -m codex8.mcp.server``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex8.core.agent.preamble import Depth, select_preamble
from codex8.core.agent.synopsis import maybe_rebuild_synopsis
from codex8.core.clients.embeddings import embed_batch, embed_text
from codex8.core.config import get_config, get_settings
from codex8.core.exploration import run_exploration
from codex8.core.knowledge_graph.builder import schedule_kg_update
from codex8.store import get_store

from .banner import CODEX8_BANNER
from .tenancy import resolve_store, resolve_tenant

logger = logging.getLogger(__name__)

mcp = FastMCP("codex8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _render_content(content: Any) -> str:
    """Render a finding's free-form ``content`` dict to a markdown body."""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return str(content)
    if not content:
        return ""

    if len(content) == 1:
        only = next(iter(content.values()))
        if isinstance(only, str):
            return only

    lines: list[str] = []
    for key, value in content.items():
        label = key.replace("_", " ").title()
        if isinstance(value, (list, dict)):
            lines.append(f"**{label}**:")
            lines.append("```json")
            lines.append(json.dumps(value, indent=2))
            lines.append("```")
        else:
            lines.append(f"**{label}**: {value}")
    return "\n".join(lines)


def _normalize_provenance(provenance: Any) -> list[dict]:
    """Keep finding provenance shape and stamp absent ``accessed_at`` values."""
    if not provenance:
        return []
    out: list[dict] = []
    for item in provenance:
        if isinstance(item, dict):
            entry = dict(item)
            entry.setdefault("accessed_at", _now_iso())
            out.append(entry)
    return out


@mcp.tool()
async def codex8_resume(
    project: str, kb: str, query: str | None = None, depth: Depth = "normal"
) -> dict:
    """Inject Codex8 KB context into this conversation.

    Returns the Codex8 banner, a ``<preamble>`` containing synopsis and
    query-relevant findings, and a ``rich``/``sparse``/``gap`` coverage band.
    """
    try:
        ctx = resolve_tenant(project, kb, create=False)
    except Exception as exc:  # noqa: BLE001 — clean error for missing project/KB
        return {"error": f"KB not found ({project}/{kb}): {exc}"}
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    preamble, coverage = await select_preamble(query, store=store, kb_id=ctx.kb_id, depth=depth)
    return {"banner": CODEX8_BANNER, "preamble": preamble, "coverage": coverage}


@mcp.tool()
async def codex8_search(project: str, kb: str, query: str, limit: int | None = None) -> dict:
    """Recall from the KB only — semantic search over existing findings, no web."""
    try:
        ctx = resolve_tenant(project, kb, create=False)
    except Exception as exc:  # noqa: BLE001 — clean error for missing project/KB
        return {"error": f"KB not found ({project}/{kb}): {exc}"}
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    embedding = await embed_text(query)
    hits = await store.match_findings(
        ctx.kb_id, embedding, match_count=limit or 10, min_similarity=0.0
    )
    return {"query": query, "findings": hits}


@mcp.tool()
async def codex8_explore(
    project: str, kb: str, prompt: str, max_findings: int | None = None
) -> dict:
    """Run research and persist findings, creating the named project/KB as needed."""
    ctx = resolve_tenant(project, kb, create=True)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    cfg = get_config().exploration
    cap = min(max_findings or cfg.default_max_findings, cfg.max_findings)

    exploration_id = store.create_exploration(ctx.org_id, ctx.kb_id, prompt)
    try:
        findings = await run_exploration(
            prompt,
            exploration_id=exploration_id,
            project_id=ctx.project_id,
            kb_id=ctx.kb_id,
            cfg=cfg,
        )
        captured = findings[:cap]

        ids: list[str] = []
        if captured:
            rows: list[dict] = []
            contents: list[str] = []
            for finding in captured:
                body = _render_content(finding.content)
                rows.append(
                    {
                        "org_id": ctx.org_id,
                        "kb_id": ctx.kb_id,
                        "title": finding.title,
                        "content": body,
                        "category": finding.category,
                        "confidence": (
                            float(finding.confidence) if finding.confidence is not None else None
                        ),
                        "tags": list(finding.tags or []),
                        "provenance": _normalize_provenance(finding.provenance),
                    }
                )
                contents.append(body)
            embeddings = await embed_batch(contents)
            for row, embedding in zip(rows, embeddings):
                row["embedding"] = embedding
            ids = await store.insert_findings(rows)

        store.update_exploration(
            exploration_id, status="completed", completed_at=_now_iso(), finding_ids=ids
        )
        await maybe_rebuild_synopsis(ctx.kb_id, org_id=ctx.org_id, store=store)
        schedule_kg_update(ctx, ids, store=store)
    except Exception as exc:  # noqa: BLE001 — mark row failed before re-raising
        store.update_exploration(
            exploration_id, status="failed", completed_at=_now_iso(), error=str(exc)
        )
        raise

    return {"exploration_id": exploration_id, "finding_ids": ids, "count": len(ids)}


@mcp.tool()
async def codex8_projects() -> dict:
    """List local projects with their KBs for client discovery."""
    return {"projects": resolve_store().list_projects()}


def main() -> None:
    get_settings()
    mcp.run()


if __name__ == "__main__":
    main()
