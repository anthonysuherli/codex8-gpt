"""Store: the engine's local persistence seam.

`Store` is the protocol and `SQLiteStore` is the local implementation.
`get_store()` accepts the upstream call-site arguments for compatibility but
always returns a cached SQLite store.
"""

from __future__ import annotations

from codex8.store.base import Store
from codex8.store.sqlite import SQLiteStore, _default_db_path

__all__ = ["Store", "SQLiteStore", "get_store", "active_backend"]

# Local stores cached by db_path so the SQLite connection is reused.
_local_stores: dict[str, SQLiteStore] = {}


def active_backend() -> str:
    """The active backend name, retained as a future tenancy seam."""
    return "local"


def get_store(access_token: str | None = None, *, org_id: str | None = None) -> Store:
    """Return a cached local SQLiteStore; arguments are accepted and ignored."""
    path = _default_db_path()
    store = _local_stores.get(path)
    if store is None:
        store = SQLiteStore(path)
        _local_stores[path] = store
    return store
