"""Resolve local MCP tenancy by project and knowledge-base name.

Codex8's MCP server is intentionally single-user and local-only: all data lives
in the local Store under the synthetic ``local`` organization and needs neither
an access token nor a cloud client.
"""

from __future__ import annotations

import uuid

from codex8.core.agent.state import TenantContext


def resolve_tenant(project: str, kb: str, *, create: bool = True) -> TenantContext:
    """Resolve a local TenantContext, creating project/KB on demand when asked."""
    from codex8.store import get_store

    store = get_store()
    org_id, project_id = store.resolve_project(project, create=create)
    kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
    return TenantContext(
        user_id="local",
        org_id="local",
        project_id=project_id,
        kb_id=kb_id,
        thread_id=str(uuid.uuid4()),
        access_token="",
    )


def resolve_store():
    """Return the single local Store for cross-project MCP reads."""
    from codex8.store import get_store

    return get_store()
