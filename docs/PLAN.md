# codex8 Port Implementation Plan

> **For the executing agent (Codex):** Execute tasks strictly in order. Each task is its
> own test cycle: write the failing test, run it, port/implement, run to green, commit.
> Steps use checkbox (`- [ ]`) syntax — check them off as you go. `SPEC.md` is the
> authority on scope; `AGENTS.md` on rules. Never edit `_upstream/`.

**Goal:** Port the delapan knowledge engine to a standalone Codex/GPT-5.6 plugin with a
single credential (`OPENAI_API_KEY`), local SQLite+sqlite-vec storage, and MCP tools
`codex8_resume` / `codex8_search` / `codex8_explore` / `codex8_projects`.

**Architecture:** Hard fork by copy+rename from the frozen snapshot in `_upstream/delapan/`
(imports `delapan.*` → `codex8.*`). Two genuinely new seams: `clients/research.py`
(GPT-5.6 hosted `web_search` + httpx page fetch, replacing Tavily) and the Codex plugin
shell (`install.sh`, `skills/`, `[mcp_servers.codex8]`). Everything else is a faithful
port with model IDs moved to GPT-5.6 tiers.

**Tech Stack:** Python 3.12, pydantic v2, openai (Responses API), mcp (FastMCP), httpx,
sqlite-vec, pytest + pytest-asyncio, ruff.

## Global Constraints

- Only credential: `OPENAI_API_KEY`. Never committed; `.env` is gitignored.
- Models: heavy = `gpt-5.6-terra`, cheap = `gpt-5.6-luna`, embeddings =
  `text-embedding-3-small` (1536 dims). Task 2 verifies real API IDs first.
- Env prefixes: `DLP_` → `C8_`; `DELAPAN_CONFIG_FILE` → `CODEX8_CONFIG_FILE`; DB default
  `~/.codex8/codex8.db`, override `CODEX8_DB_PATH`.
- No network in tests. Mock every OpenAI call; SQLite in `tmp_path`; fake embeddings =
  `[0.1] * 1536` variants.
- Style: `from __future__ import annotations`, type hints, module docstring with ASCII
  flow diagram, ruff line-length 100.
- Commit after every task (or where a task says so). Never squash.

---

## Phase 0 — Bootstrap

### Task 1: Repo skeleton + upstream snapshot commit

**Files:**
- Commit as-is: `_upstream/delapan/` (already vendored by scaffolding), `SPEC.md`,
  `AGENTS.md`, `docs/PLAN.md`, `docs/CODEX-SESSION.md`, `README.md`, `LICENSE`,
  `.gitignore`, `.env.example`
- Create: `pyproject.toml`, `codex8/__init__.py`, `tests/conftest.py`

**Interfaces:**
- Produces: installable package `codex8`, `pytest` runs, `FAKE_EMBEDDING` fixture.

- [ ] **Step 1: Commit the prior-work snapshot separately (evidence boundary)**

```bash
git add _upstream/
git commit -m "chore: import frozen upstream delapan engine snapshot (prior work, read-only)"
git add SPEC.md AGENTS.md docs/ README.md LICENSE .gitignore .env.example
git commit -m "chore: scaffold — spec, plan, agent instructions"
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "codex8"
version = "0.1.0"
description = "Knowledge engine plugin for Codex — GPT-5.6 as the only agent, one API key, local-first"
requires-python = ">=3.12"
license = { file = "LICENSE" }
dependencies = [
  "pydantic>=2.12.5",
  "pydantic-settings>=2.12.0",
  "pyyaml>=6.0.3",
  "httpx>=0.28.1",
  "openai>=2.7.0",
  "mcp>=1.9.0",
  "sqlite-vec>=0.1.6",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=1.0", "ruff>=0.11"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["codex8"]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Create the package and shared fixtures**

`codex8/__init__.py`:

```python
"""codex8 — knowledge engine plugin for Codex. GPT-5.6 only, one key, local-first."""
```

`tests/conftest.py`:

```python
from __future__ import annotations

import pytest


@pytest.fixture
def fake_embedding() -> list[float]:
    return [0.1] * 1536


@pytest.fixture
def fake_embedding_other() -> list[float]:
    return [-0.1] * 1536
```

- [ ] **Step 4: Verify install + empty test run**

Run: `uv venv && uv pip install -e ".[dev]" && .venv/bin/pytest`
Expected: `no tests ran` (exit code 5 is fine at this point).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml codex8/__init__.py tests/conftest.py
git commit -m "chore: package skeleton, deps, test fixtures"
```

---

## Phase 1 — Engine port

### Task 2: config.py — Settings, AppConfig, config.yaml

**Files:**
- Create: `codex8/core/__init__.py` (empty), `codex8/core/config.py` (port of
  `_upstream/delapan/core/config.py`), `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `get_settings() -> Settings` (field `openai_api_key: str | None`),
  `get_config() -> AppConfig` (sections: `search`, `tiers`, `synopsis`, `exploration`,
  `narration`, `deepen`, `embedding`, `knowledge_graph`, `concepts`, `prompts`).
  Both `@lru_cache`'d, exactly as upstream.

- [ ] **Step 0: Verify GPT-5.6 API model IDs (one manual check, before any code)**

Run: `curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['data'] if '5.6' in m['id'] or 'embedding' in m['id']])"`
Expected: IDs containing `gpt-5.6` tiers and `text-embedding-3-small`. If the tier slugs
differ from `gpt-5.6-terra` / `gpt-5.6-luna`, use the real IDs in every step below and in
`config.yaml`, and note the substitution in the commit message.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from __future__ import annotations

from codex8.core.config import get_config, get_settings


def test_settings_only_openai_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_api_key == "sk-test"
    assert not hasattr(s, "tavily_api_key")
    assert not hasattr(s, "ai_gateway_api_key")
    assert not hasattr(s, "supabase_url")


def test_config_defaults_are_gpt56(monkeypatch):
    monkeypatch.delenv("CODEX8_CONFIG_FILE", raising=False)
    get_config.cache_clear()
    cfg = get_config()
    assert cfg.exploration.planner_model == "gpt-5.6-terra"
    assert cfg.exploration.extraction_fallback_model == "gpt-5.6-luna"
    assert cfg.synopsis.model == "gpt-5.6-luna"
    assert cfg.embedding.model == "text-embedding-3-small"
    assert cfg.embedding.dim == 1536


def test_env_override_uses_c8_prefix(monkeypatch):
    monkeypatch.setenv("C8_TIERS__RICH_HIT_COUNT", "7")
    get_config.cache_clear()
    assert get_config().tiers.rich_hit_count == 7
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codex8.core'`

- [ ] **Step 3: Port config.py**

```bash
mkdir -p codex8/core && touch codex8/core/__init__.py
cp _upstream/delapan/core/config.py codex8/core/config.py
```

Then edit `codex8/core/config.py`:

1. Replace every `delapan` string/identifier: imports `delapan.` → `codex8.`, env prefix
   `DLP_` → `C8_`, `DELAPAN_CONFIG_FILE` → `CODEX8_CONFIG_FILE`, docstring product name.
2. Replace the entire `Settings` class body's fields with the single-key surface (keep
   `model_config`, adapting `env_file` resolution as upstream does):

```python
class Settings(BaseSettings):
    """Secrets + deployment identity. One credential: the OpenAI API key."""

    openai_api_key: str | None = None
    codex8_db_path: str | None = None
```

   Delete the CORS validator and any field referencing gateway/tavily/supabase/anthropic.
3. Delete `AgentConfig` and `UserProfileConfig` classes and their slots on `AppConfig`
   (the chat agent and profile injection are not ported — SPEC scope cuts).
4. Model defaults, exact edits:

   | class.field | new value |
   |---|---|
   | `SynopsisConfig.model` | `"gpt-5.6-luna"` |
   | `ExplorationConfig.planner_model` | `"gpt-5.6-terra"` |
   | `ExplorationConfig.extraction_model` | `"gpt-5.6-terra"` |
   | `ExplorationConfig.extraction_fallback_model` | `"gpt-5.6-luna"` |
   | `ExplorationConfig.evaluation_model` | `"gpt-5.6-terra"` |
   | `NarrationConfig.model` | `"gpt-5.6-luna"` |
   | `OKFConfig.model` | `"gpt-5.6-terra"` |
   | `DeepenConfig.decompose_model` / `.critic_model` | `"gpt-5.6-terra"` |
   | `KnowledgeGraphConfig.extraction_model` | `"gpt-5.6-terra"` |
   | `KnowledgeGraphConfig.extraction_fallback_model` | `"gpt-5.6-luna"` |
   | `ConceptsConfig.extract_model` | `"gpt-5.6-terra"` |

5. Add to `ExplorationConfig` (used by Task 4's researcher):

```python
    research_model: str = "gpt-5.6-luna"  # drives the hosted web_search tool
```

6. Update the comments that say models are "routed through Vercel AI Gateway" to say
   "OpenAI API model IDs".

- [ ] **Step 4: Write `config.yaml`** — port `_upstream`'s `config.yaml` structure with the
  same knobs minus `agent:` and `user_profile:` sections, all model values matching the
  table above, and the header comment explaining `C8_<SECTION>__<FIELD>` overrides.

- [ ] **Step 5: Run to green**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add codex8/core/ config.yaml tests/test_config.py
git commit -m "feat: config — single-key Settings, GPT-5.6 model defaults, C8_ env overrides"
```

### Task 3: OpenAI client + embeddings

**Files:**
- Create: `codex8/core/clients/__init__.py` (empty), `codex8/core/clients/openai_client.py`
  (port of `_upstream/delapan/core/clients/ai_gateway.py`), `codex8/core/clients/embeddings.py`
  (port of `_upstream/delapan/core/clients/embeddings.py`)
- Test: `tests/test_clients.py`

**Interfaces:**
- Produces: `openai_client.client() -> AsyncOpenAI`,
  `text_completion(...)` and `structured_completion(...)` with signatures identical to
  upstream `ai_gateway` (later tasks' ported modules import them by these names), and
  `embeddings.embed_text(text) -> list[float]`, `embed_batch(texts) -> list[list[float]]`,
  `embed_with_retry(text, retries=2) -> list[float]`.

- [ ] **Step 1: Write the failing test**

`tests/test_clients.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import codex8.core.clients.embeddings as emb_mod
import codex8.core.clients.openai_client as oc


def _fake_openai(monkeypatch, module, **attrs):
    fake = SimpleNamespace(**attrs)
    monkeypatch.setattr(module, "_get_client", lambda: fake, raising=False)
    monkeypatch.setattr(module, "client", lambda: fake, raising=False)
    return fake


async def test_embed_text_uses_configured_model_and_dim(monkeypatch, fake_embedding):
    create = AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(embedding=fake_embedding)]))
    _fake_openai(monkeypatch, emb_mod, embeddings=SimpleNamespace(create=create))
    vec = await emb_mod.embed_text("hello")
    assert len(vec) == 1536
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["dimensions"] == 1536


async def test_client_points_at_openai_not_gateway(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from codex8.core.config import get_settings

    get_settings.cache_clear()
    c = oc.client()
    assert "openai" in str(c.base_url)  # default https://api.openai.com/v1 — no gateway
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codex8.core.clients'`

- [ ] **Step 3: Port both modules**

```bash
mkdir -p codex8/core/clients && touch codex8/core/clients/__init__.py
cp _upstream/delapan/core/clients/ai_gateway.py codex8/core/clients/openai_client.py
cp _upstream/delapan/core/clients/embeddings.py codex8/core/clients/embeddings.py
```

Edits in `openai_client.py`: rename imports to `codex8.*`; rename `gateway_client()` →
`client()`; construct `AsyncOpenAI(api_key=s.openai_api_key)` with **no** `base_url`;
update the module docstring flow diagram; keep `text_completion` / `structured_completion`
bodies and signatures byte-identical apart from the client call.

Edits in `embeddings.py`: rename imports; `_get_client()` returns
`AsyncOpenAI(api_key=settings.openai_api_key)` (no gateway branch, no `base_url`); keep
both `dimensions=emb.dim` arguments exactly as upstream.

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_clients.py -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add codex8/core/clients/ tests/test_clients.py
git commit -m "feat: OpenAI-direct LLM + embeddings clients (fork of ai_gateway, no gateway)"
```

### Task 4: research.py — web research without Tavily (NEW code)

**Files:**
- Create: `codex8/core/clients/research.py`, `scripts/smoke_research.py`
- Test: `tests/test_research.py`

**Interfaces:**
- Produces: `search(query, *, max_results, search_depth) -> list[dict]` (each dict:
  `url`, `title`, `content`) and `extract(urls, *, search_depth="advanced") -> dict[str, str]`
  — signature-compatible with upstream `clients/tavily.py`, so Task 7's engine swap is
  import-only.

- [ ] **Step 1: Write the failing test**

`tests/test_research.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import codex8.core.clients.research as research


def _fake_response(text: str, citations: list[tuple[str, str]]):
    annotations = [
        SimpleNamespace(type="url_citation", url=u, title=t) for u, t in citations
    ]
    message = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text, annotations=annotations)],
    )
    return SimpleNamespace(output=[message], output_text=text)


async def test_search_returns_cited_sources(monkeypatch):
    fake = _fake_response(
        "Summary of results.",
        [("https://a.example/one", "One"), ("https://b.example/two", "Two")],
    )
    create = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        research, "_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    results = await research.search("test query", max_results=1, search_depth="basic")
    assert results == [{"url": "https://a.example/one", "title": "One", "content": "Summary of results."}]
    assert create.call_args.kwargs["tools"] == [{"type": "web_search"}]


async def test_extract_strips_html(monkeypatch):
    async def fake_get(url, **kwargs):
        return SimpleNamespace(
            text="<html><script>x()</script><body><h1>Title</h1><p>Body text.</p></body></html>",
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(research, "_http_get", fake_get)
    out = await research.extract(["https://a.example/one"])
    assert "Body text." in out["https://a.example/one"]
    assert "script" not in out["https://a.example/one"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_research.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Implement `codex8/core/clients/research.py`**

```python
"""Web research via GPT-5.6 hosted web_search + plain HTTP fetch — replaces Tavily.

    search(query)  ──► Responses API (tools=[web_search]) ──► url_citation annotations
    extract(urls)  ──► httpx GET ──► stdlib HTML→text ──► {url: text}

Single-key by design: search rides the OpenAI hosted tool, extraction is keyless HTTP.
Signature-compatible with the upstream ``clients/tavily.py`` surface.
"""

from __future__ import annotations

import asyncio
import logging
from html.parser import HTMLParser
from io import StringIO

import httpx
from openai import AsyncOpenAI

from codex8.core.config import get_config, get_settings

logger = logging.getLogger(__name__)

_MAX_PAGE_CHARS = 40_000
_FETCH_TIMEOUT = 20.0


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


class _TextExtractor(HTMLParser):
    """Minimal HTML→text: drops script/style, keeps visible text with newlines."""

    _SKIP = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out = StringIO()
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self._out.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._out.write(data)

    def text(self) -> str:
        lines = (ln.strip() for ln in self._out.getvalue().splitlines())
        return "\n".join(ln for ln in lines if ln)


async def _http_get(url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, timeout=_FETCH_TIMEOUT) as http:
        return await http.get(url, headers={"User-Agent": "codex8-research/0.1"}, **kwargs)


async def search(query: str, *, max_results: int, search_depth: str = "basic") -> list[dict]:
    """Hosted web_search; returns [{url, title, content}] like Tavily's search.

    ``search_depth`` is accepted for signature compatibility and ignored — depth is the
    model's concern. ``content`` carries the model's synthesized summary (the extractor
    reads full pages via :func:`extract` anyway).
    """
    cfg = get_config().exploration
    resp = await _client().responses.create(
        model=cfg.research_model,
        tools=[{"type": "web_search"}],
        input=(
            "Search the web and report the most relevant, recent sources for: "
            f"{query}\nCite every source."
        ),
    )
    text = getattr(resp, "output_text", "") or ""
    results: list[dict] = []
    seen: set[str] = set()
    for item in resp.output or []:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                url = getattr(ann, "url", None)
                if getattr(ann, "type", "") == "url_citation" and url and url not in seen:
                    seen.add(url)
                    results.append({"url": url, "title": getattr(ann, "title", url), "content": text})
    return results[:max_results]


async def extract(urls: list[str], *, search_depth: str = "advanced") -> dict[str, str]:
    """Fetch pages over plain HTTP and reduce to visible text — {url: text}."""

    async def one(url: str) -> tuple[str, str]:
        try:
            resp = await _http_get(url)
            resp.raise_for_status()
            parser = _TextExtractor()
            parser.feed(resp.text)
            return url, parser.text()[:_MAX_PAGE_CHARS]
        except Exception as exc:  # noqa: BLE001 — a dead page must not kill the run
            logger.warning("extract failed for %s: %s", url, exc)
            return url, ""

    pairs = await asyncio.gather(*(one(u) for u in urls))
    return {url: text for url, text in pairs if text}
```

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_research.py -v` → 2 passed.

- [ ] **Step 5: Write `scripts/smoke_research.py`** (manual, live — NOT collected by pytest)

```python
"""Live smoke: python scripts/smoke_research.py 'your query' — needs OPENAI_API_KEY."""

from __future__ import annotations

import asyncio
import sys

from codex8.core.clients.research import extract, search


async def main() -> None:
    results = await search(sys.argv[1], max_results=3)
    for r in results:
        print(r["url"], "—", r["title"])
    pages = await extract([r["url"] for r in results])
    for url, text in pages.items():
        print(f"\n=== {url} ({len(text)} chars) ===\n{text[:300]}")


asyncio.run(main())
```

Run it once with a real key: `.venv/bin/python scripts/smoke_research.py "sqlite-vec"`.
Expected: ≥1 URL printed with non-empty page text. If the Responses API annotation shape
differs from the mocked one, fix `search()` to match reality and re-run both the unit
tests and this smoke — reality wins over the mock.

- [ ] **Step 6: Commit**

```bash
git add codex8/core/clients/research.py tests/test_research.py scripts/smoke_research.py
git commit -m "feat: research client — hosted web_search + keyless page extraction (Tavily replaced)"
```

### Task 5: Store — SQLite + sqlite-vec

**Files:**
- Create: `codex8/store/__init__.py`, `codex8/store/base.py`, `codex8/store/sqlite.py`
  (ports of `_upstream/delapan/store/{__init__,base,sqlite}.py`)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `get_store(access_token: str = "", org_id: str = "local") -> SQLiteStore`
  (always SQLite — the supabase branch is deleted), and the full upstream `Store` method
  surface used later: `match_findings`, `insert_findings`, `create_exploration`,
  project/KB find-or-create resolution, synopsis read/write, KG node/edge upserts.

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:

```python
from __future__ import annotations

from codex8.store import get_store
from codex8.store.sqlite import SQLiteStore


def _store(tmp_path) -> SQLiteStore:
    return SQLiteStore(db_path=str(tmp_path / "t.db"))


async def test_insert_then_match_roundtrip(tmp_path, fake_embedding, fake_embedding_other):
    s = _store(tmp_path)
    kb_id = s.resolve_kb(s.resolve_project("p1"), "kb1")
    rows = [
        {"kb_id": kb_id, "title": "near", "content": "near finding", "embedding": fake_embedding},
        {"kb_id": kb_id, "title": "far", "content": "far finding", "embedding": fake_embedding_other},
    ]
    ids = await s.insert_findings(rows)
    assert len(ids) == 2
    hits = await s.match_findings(kb_id, fake_embedding, limit=1)
    assert hits[0]["title"] == "near"
    assert hits[0]["similarity"] > 0.99


def test_get_store_is_always_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "env.db"))
    assert isinstance(get_store(), SQLiteStore)
```

NOTE: upstream method names/signatures win — if `resolve_project`/`resolve_kb` differ in
`_upstream/delapan/store/sqlite.py` (e.g. a single find-or-create helper), adapt the TEST
to the ported reality before adapting any implementation. The port is faithful; the test
follows it.

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: codex8.store`.

- [ ] **Step 3: Port the three files**

```bash
mkdir -p codex8/store
cp _upstream/delapan/store/base.py codex8/store/base.py
cp _upstream/delapan/store/sqlite.py codex8/store/sqlite.py
cp _upstream/delapan/store/__init__.py codex8/store/__init__.py
```

Edits: rename imports `delapan.*` → `codex8.*`; default DB path `~/.delapan/delapan.db` →
`~/.codex8/codex8.db` honoring `CODEX8_DB_PATH` / `Settings.codex8_db_path`; in
`__init__.py`'s `get_store`, delete the supabase/cloud branch and its lazy import so it
returns `SQLiteStore` unconditionally; delete `store/supabase.py` references. Schema DDL,
`vec0 float[1536]` tables, and cosine KNN SQL stay byte-identical.

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_store.py -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add codex8/store/ tests/test_store.py
git commit -m "feat: local-only store — SQLite + sqlite-vec, cloud branch removed"
```

### Task 6: Agent — preamble, synopsis, state, concept_doc

**Files:**
- Create: `codex8/core/agent/{__init__,state,synopsis,preamble,concept_doc}.py`
  (ports of `_upstream/delapan/core/agent/*`)
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `text_completion` (Task 3), `embed_text` (Task 3), store surface (Task 5).
- Produces: `select_preamble(...)` + `Depth`, `maybe_rebuild_synopsis(...)`,
  `load_synopsis(...)`, `TenantContext` — exactly the names `mcp/server.py` imports.

- [ ] **Step 1: Write the failing test**

`tests/test_agent.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.core.agent.preamble as preamble_mod
from codex8.core.agent.preamble import select_preamble
from codex8.core.agent.state import TenantContext
from codex8.store.sqlite import SQLiteStore


async def test_preamble_coverage_gap_on_empty_kb(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setattr(preamble_mod, "embed_text", AsyncMock(return_value=fake_embedding))
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = s.resolve_kb(s.resolve_project("p"), "kb")
    result = await select_preamble(s, kb_id, query="anything", depth="normal")
    assert result["coverage"] == "gap"
    assert "<preamble>" in result["preamble"]


def test_tenant_context_shape():
    ctx = TenantContext(org_id="local", user_id="local", access_token="", project_id="x", kb_id="y")
    assert ctx.org_id == "local"
```

NOTE: as in Task 5 — check `select_preamble`'s real signature and return shape in
`_upstream/delapan/core/agent/preamble.py` first and adapt the test to the ported truth
(the MCP server's `delapan_resume` shows the expected `banner/preamble/coverage` contract).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the four modules**

```bash
mkdir -p codex8/core/agent && touch codex8/core/agent/__init__.py
for f in state synopsis preamble concept_doc; do
  cp "_upstream/delapan/core/agent/$f.py" "codex8/core/agent/$f.py"
done
```

Edits — all files: rename imports `delapan.*` → `codex8.*` and
`clients.ai_gateway` → `clients.openai_client`. Then the one real seam, in `synopsis.py`:
it imports `from delapan.core.clients.anthropic import chat_model`. Delete that import and
rewrite its single LLM call site to use
`from codex8.core.clients.openai_client import text_completion` with
`model=cfg.model` (now `gpt-5.6-luna`), preserving the exact prompt strings and the shape
of the parsed response — mirror how `concept_doc.py` already calls `text_completion`.

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_agent.py -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add codex8/core/agent/ tests/test_agent.py
git commit -m "feat: agent layer — preamble/synopsis/concepts on GPT-5.6 (anthropic client removed)"
```

### Task 7: Exploration pipeline

**Files:**
- Create: `codex8/core/exploration/{__init__,models,planner,extractor,merger,evaluator,narrator,deepen,engine}.py`
  (ports of `_upstream/delapan/core/exploration/*`)
- Test: `tests/test_exploration.py`

**Interfaces:**
- Consumes: `structured_completion`/`text_completion` (Task 3), `research.search`/`research.extract`
  (Task 4), `ExplorationConfig` (Task 2).
- Produces: `run_exploration(prompt, *, exploration_id, project_id, kb_id, cfg) -> list`
  (re-exported from `codex8.core.exploration` exactly as upstream's `__init__.py` does).

- [ ] **Step 1: Write the failing test**

`tests/test_exploration.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.core.exploration.engine as engine_mod


async def test_engine_uses_research_not_tavily(monkeypatch):
    assert not hasattr(engine_mod, "tavily")
    assert hasattr(engine_mod, "research")


async def test_run_exploration_smoke(monkeypatch):
    from codex8.core.config import get_config
    from codex8.core.exploration import run_exploration

    monkeypatch.setattr(
        engine_mod.research, "search",
        AsyncMock(return_value=[{"url": "https://x.example/a", "title": "A", "content": "snippet"}]),
    )
    monkeypatch.setattr(
        engine_mod.research, "extract",
        AsyncMock(return_value={"https://x.example/a": "Full page text about the topic."}),
    )
    # Plan/extract/merge LLM calls: mock structured_completion at each consumer module.
    import codex8.core.exploration.planner as planner_mod
    import codex8.core.exploration.extractor as extractor_mod

    monkeypatch.setattr(
        planner_mod, "structured_completion",
        AsyncMock(return_value={"queries": ["q1"]}),
    )
    monkeypatch.setattr(
        extractor_mod, "structured_completion",
        AsyncMock(return_value={"findings": [{"title": "F1", "content": {"fact": "x"}, "category": "c"}]}),
    )
    findings = await run_exploration(
        "topic", exploration_id="e1", project_id="p1", kb_id="k1",
        cfg=get_config().exploration,
    )
    assert findings
```

NOTE: the planner/extractor mock return shapes above are guesses — before running, open
`_upstream/delapan/core/exploration/{planner,extractor}.py`, read the schemas they pass to
`structured_completion`, and make the mocks return exactly those shapes. Also mirror any
other pipeline stages `run_exploration` awaits (evaluator, merger, deepen, narrator) with
mocks matching their real contracts, or configure them off via `ExplorationConfig` knobs
if upstream exposes toggles. The assertion stands: with all externals mocked,
`run_exploration` returns a non-empty findings list.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port all eight modules**

```bash
mkdir -p codex8/core/exploration
for f in __init__ models planner extractor merger evaluator narrator deepen engine; do
  cp "_upstream/delapan/core/exploration/$f.py" "codex8/core/exploration/$f.py"
done
```

Edits — all files: `delapan.*` → `codex8.*`, `clients.ai_gateway` → `clients.openai_client`.
In `engine.py` only: `from codex8.core.clients import research` replaces
`from delapan.core.clients import tavily`, then `tavily.search(` → `research.search(` and
`tavily.extract(` → `research.extract(` (the Task 4 surface is signature-compatible, so
nothing else changes).

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_exploration.py -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add codex8/core/exploration/ tests/test_exploration.py
git commit -m "feat: exploration pipeline on GPT-5.6 — research client replaces tavily at the engine seam"
```

### Task 8: Knowledge graph

**Files:**
- Create: `codex8/core/knowledge_graph/{__init__,models,schema,extractor,builder,service}.py`
  (ports of `_upstream/delapan/core/knowledge_graph/*`)
- Test: `tests/test_knowledge_graph.py`

**Interfaces:**
- Consumes: `structured_completion` (Task 3), store KG surface (Task 5).
- Produces: `schedule_kg_update(...)` (imported by `mcp/server.py`), `read_graph(...)`
  (imported by `concept_doc.py` — Task 6 already references it, so this task makes the
  agent package import cleanly end-to-end).

- [ ] **Step 1: Write the failing test**

`tests/test_knowledge_graph.py`:

```python
from __future__ import annotations

import codex8.core.agent.concept_doc  # noqa: F401 — resolves only when kg package exists


def test_kg_package_imports():
    from codex8.core.knowledge_graph.builder import schedule_kg_update
    from codex8.core.knowledge_graph.service import read_graph

    assert callable(schedule_kg_update) and callable(read_graph)
```

Then add one behavioral test after reading `_upstream/delapan/core/knowledge_graph/service.py`:
seed a `tmp_path` SQLiteStore with two KG nodes and one edge via the store's KG methods and
assert `read_graph` returns them. Write it against the real signatures.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the six modules** (same copy+rename recipe; imports only —
  `delapan.*` → `codex8.*`, `ai_gateway` → `openai_client`).

- [ ] **Step 4: Run the FULL suite to green** — `.venv/bin/pytest -v` (this is the first
  point where every `codex8.core` package must import cleanly together).

- [ ] **Step 5: Commit**

```bash
git add codex8/core/knowledge_graph/ tests/test_knowledge_graph.py
git commit -m "feat: knowledge graph port — finding→KG extraction on GPT-5.6"
```

---

## Phase 2 — Codex plugin surface

### Task 9: MCP server

**Files:**
- Create: `codex8/mcp/{__init__,server,tenancy,banner}.py` (ports of `_upstream/delapan/mcp/*`)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: everything above.
- Produces: MCP tools `codex8_resume`, `codex8_search`, `codex8_explore`,
  `codex8_projects`; `python -m codex8.mcp.server` runs a stdio server.

- [ ] **Step 1: Write the failing test**

`tests/test_mcp_server.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.mcp.server as server


async def test_resume_returns_contract_keys(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "embed_text", AsyncMock(return_value=fake_embedding))
    out = await server.codex8_resume(project="p", kb="k", query="q")
    assert set(out) >= {"banner", "preamble", "coverage"}
    assert out["coverage"] in {"rich", "sparse", "gap"}


async def test_projects_lists_created_kb(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setenv("CODEX8_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "embed_text", AsyncMock(return_value=fake_embedding))
    await server.codex8_resume(project="p", kb="k", query=None)
    out = await server.codex8_projects()
    names = [p["project"] for p in out["projects"]]
    assert "p" in names
```

(If `codex8_resume` triggers synopsis rebuild LLM calls on first touch, mock
`server.maybe_rebuild_synopsis` with `AsyncMock(return_value=None)` — check the upstream
call order in `_upstream/delapan/mcp/server.py` and mock at the server module, same
pattern as `embed_text` above.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the four modules**

```bash
mkdir -p codex8/mcp
for f in __init__ server tenancy banner; do cp "_upstream/delapan/mcp/$f.py" "codex8/mcp/$f.py"; done
```

Edits: rename imports; rename the four tool functions `delapan_*` → `codex8_*` (decorator
and docstrings included); in `tenancy.py` delete the cloud branch (`_login`,
`_service_client`, `_org_for`, and the `active_backend()` fork) so `resolve_tenant` /
`resolve_store` always take the local path (`org_id="local"`, empty token); in `banner.py`
swap the wordmark text to `c o d e x 8` keeping the layout. Server name string in the
FastMCP constructor → `"codex8"`.

- [ ] **Step 4: Run to green, then boot check**

Run: `.venv/bin/pytest tests/test_mcp_server.py -v` → 2 passed.
Run: `printf '' | .venv/bin/python -m codex8.mcp.server; echo "exit=$?"`
Expected: starts and exits cleanly on closed stdin (no traceback).

- [ ] **Step 5: Commit**

```bash
git add codex8/mcp/ tests/test_mcp_server.py
git commit -m "feat: MCP server — codex8_resume/search/explore/projects, local-only tenancy"
```

### Task 10: Codex skills + installer

**Files:**
- Create: `skills/resume/SKILL.md`, `skills/search/SKILL.md`, `skills/explore/SKILL.md`,
  `skills/projects/SKILL.md`, `install.sh`, `.env.example` (already scaffolded — verify)

**Interfaces:**
- Consumes: tool names from Task 9.
- Produces: a Codex-discoverable plugin — `[mcp_servers.codex8]` in `~/.codex/config.toml`
  plus skills under `~/.codex/skills/codex8-*`.

- [ ] **Step 1: Write the four skills.** Frontmatter format: `name` + `description`.
  Content pattern (write all four; `resume` shown in full):

`skills/resume/SKILL.md`:

```markdown
---
name: codex8-resume
description: Tap the codex8 KB and return a preamble-first resume card with coverage banding (rich/sparse/gap). Use before answering project-specific questions or when asked "where did I leave off".
---

# codex8 resume

1. Resolve target: project = repo folder name, kb = current git branch (fall back to
   "main"). The user can override both.
2. Call the `codex8_resume` MCP tool with `{project, kb, query?, depth}` — `query` is the
   user's question when there is one.
3. Lead your reply with the returned `banner`, then answer FROM the `<preamble>` content.
4. If `coverage` is `gap` or `sparse`, say so and offer `codex8-explore` to fill it.
```

`skills/search/SKILL.md` — same shape: call `codex8_search` with `{project, kb, query, limit?}`,
answer from ranked findings, cite finding titles.
`skills/explore/SKILL.md` — call `codex8_explore` with `{project, kb, prompt}`; warn it
blocks 1–3 minutes and needs `OPENAI_API_KEY`; afterwards re-run `codex8_resume`.
`skills/projects/SKILL.md` — call `codex8_projects`, render the project/KB table.

- [ ] **Step 2: Write `install.sh`**

```bash
#!/usr/bin/env bash
# codex8 installer — wires the MCP server into ~/.codex/config.toml and links skills.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${CODEX_HOME:-$HOME/.codex}/config.toml"
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"

[ -x "$REPO/.venv/bin/python" ] || { echo "run: uv venv && uv pip install -e . first"; exit 1; }

mkdir -p "$(dirname "$CONFIG")" "$SKILLS_DIR"
touch "$CONFIG"

if grep -q '^\[mcp_servers\.codex8\]' "$CONFIG"; then
  echo "config.toml already has [mcp_servers.codex8] — leaving it untouched"
else
  printf '\n[mcp_servers.codex8]\ncommand = "%s"\nargs = ["-m", "codex8.mcp.server"]\n' \
    "$REPO/.venv/bin/python" >> "$CONFIG"
  echo "registered [mcp_servers.codex8] in $CONFIG"
fi

for s in resume search explore projects; do
  ln -sfn "$REPO/skills/$s" "$SKILLS_DIR/codex8-$s"
done
echo "linked skills: codex8-{resume,search,explore,projects} → $SKILLS_DIR"
echo "done — restart Codex to pick up the server."
```

- [ ] **Step 3: Verify the installer is idempotent**

Run: `chmod +x install.sh && ./install.sh && ./install.sh`
Expected: second run prints "already has … leaving it untouched"; `grep -c 'mcp_servers.codex8' ~/.codex/config.toml` → 1.

- [ ] **Step 4: Live plugin check** — open a NEW Codex session in any folder and confirm
  the `codex8_projects` tool is callable and skills appear. This is the Phase 2 gate.

- [ ] **Step 5: Commit**

```bash
git add skills/ install.sh
git commit -m "feat: Codex plugin shell — skills + config.toml installer"
```

### Task 11: Demo KB — judge path without exploration

**Files:**
- Create: `scripts/seed_demo.py`, `data/demo.db` (built artifact, committed),
  `data/demo_findings.json` (source of truth, committed)

**Interfaces:**
- Consumes: store (Task 5), embeddings (Task 3).
- Produces: a committed KB (`project="codex8-demo"`, `kb="build-week"`) so judges get
  ranked recall for the cost of one query-embedding call — no exploration required.

- [ ] **Step 1: Author `data/demo_findings.json`** — 15–25 findings about codex8 itself
  and OpenAI Build Week (title, content, category, provenance url). Write them by hand
  from `SPEC.md` and the hackathon rules; this doubles as the demo script's material.

- [ ] **Step 2: Write `scripts/seed_demo.py`**

```python
"""Build data/demo.db from data/demo_findings.json — run once with OPENAI_API_KEY set.

    demo_findings.json ──► embed_batch ──► SQLiteStore(data/demo.db) ──► committed artifact
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from codex8.core.clients.embeddings import embed_batch
from codex8.store.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    findings = json.loads((ROOT / "data" / "demo_findings.json").read_text())
    db = ROOT / "data" / "demo.db"
    db.unlink(missing_ok=True)
    store = SQLiteStore(db_path=str(db))
    kb_id = store.resolve_kb(store.resolve_project("codex8-demo"), "build-week")
    vecs = await embed_batch([f["content"] for f in findings])
    rows = [{**f, "kb_id": kb_id, "embedding": v} for f, v in zip(findings, vecs, strict=True)]
    ids = await store.insert_findings(rows)
    print(f"seeded {len(ids)} findings into {db}")


asyncio.run(main())
```

(Adapt the row dict to the exact `insert_findings` shape ported in Task 5 — same NOTE as
Task 5: the ported reality wins.)

- [ ] **Step 3: Build and verify**

Run: `.venv/bin/python scripts/seed_demo.py` then
`CODEX8_DB_PATH=data/demo.db .venv/bin/python -c "import asyncio; from codex8.mcp.server import codex8_search; print(asyncio.run(codex8_search(project='codex8-demo', kb='build-week', query='what is codex8')))"`
Expected: ranked findings with similarities.

- [ ] **Step 4: Commit** (yes, the .db is committed — it IS the judge sandbox)

```bash
git add scripts/seed_demo.py data/
git commit -m "feat: pre-seeded demo KB — judge path with zero exploration cost"
```

---

## Phase 3 — Submission polish

### Task 12: E2E verification, README, evidence capture

**Files:**
- Modify: `README.md` (replace stub sections)

- [ ] **Step 1: Full-suite + lint gate** — `.venv/bin/pytest && .venv/bin/ruff check .` green.

- [ ] **Step 2: Live E2E in a fresh Codex session** (the acceptance criteria from SPEC.md):
  demo-KB resume + search; then one real `codex8_explore` on a novel prompt; then
  `codex8_resume` again showing the coverage upgrade. Screen-record this — it is the demo
  video's spine.

- [ ] **Step 3: README final.** Sections, in order: what codex8 is (3 sentences);
  Quick start (clone → `uv venv && uv pip install -e .` → `./install.sh` → restart Codex);
  Judge quick-path (demo KB commands, exact); Supported platforms (macOS + Linux; Windows
  untested); Architecture (the SPEC tree, condensed); **"Built with Codex"** — the honest
  narrative of how Codex executed this plan, which tasks it accelerated, where key
  decisions were made, with commit-range references; Roadmap (cloud tier, multi-agent
  explore); License.

- [ ] **Step 4: Evidence capture** — run `/feedback` in THIS Codex thread, save the
  session ID into the Devpost submission draft (NOT into the repo).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README — install, judge path, Codex collaboration narrative"
```

---

## Self-review notes (already applied)

- Spec coverage: constraints 1–5 → Tasks 2–4 (single key, GPT-5.6), 5 (local-first),
  11 (judge path), 1+12 (evidence). Scope cuts enforced in Tasks 2 (Settings/AgentConfig),
  5 (get_store), 9 (tenancy). Surface table → Task 9. Acceptance checklist → Task 12.
- Known unknowns are marked inline as NOTEs (store method names, `select_preamble`
  signature, planner/extractor schemas, Responses API annotation shape): in each case the
  instruction is the same — **read the `_upstream` source / observe the live API first,
  adapt the test to the ported reality, keep the port faithful.**
- The stretch differentiator (multi-agent explore) is deliberately NOT a task — it enters
  only if Tasks 1–12 are done and verified before 2026-07-20.
