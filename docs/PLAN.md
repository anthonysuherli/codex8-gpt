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

## Reference execution

This plan was **fully executed and verified** in a reference build at `../codex8-ref`:
26/26 tests pass, `ruff check` + `ruff format --check` are clean, and the MCP server
boots and exits cleanly on closed stdin. The reference history is the 12 task commits
plus two review-fix commits landed after them: `c41b09c` (Task 4 — `search()` retry +
return-`[]` failure contract) and `119c0e3` (Task 11 — hand-authored synopsis spine for
keyless resume); both fixes are already folded into the task text and code blocks below.
**Treat the code blocks in this plan as verified-correct and copy them verbatim** (they
are already ruff-formatted; do not "fix" them to match upstream where they differ, the
difference IS the correction).

The reference build had no `OPENAI_API_KEY`, so the following **LIVE** steps remain
unexecuted and are the re-executor's responsibility:

- Task 2 Step 0 — the model-ID `curl` against `GET /v1/models`.
- Task 4 Step 5 — the `scripts/smoke_research.py` live smoke.
- Task 11 Step 4 — building and committing `data/demo.db`. A `data/demo.db` exists in
  the reference build, but the judged repo must still build its own here with the
  operator's real OpenAI key (the artifact's embeddings and commit must originate in
  this repo).
- Task 10 Step 5 and Task 12 Step 2 — live Codex session checks.

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

- [x] **Step 1: Commit the prior-work snapshot separately (evidence boundary)**

```bash
git add _upstream/
git commit -m "chore: import frozen upstream delapan engine snapshot (prior work, read-only)"
git add SPEC.md AGENTS.md docs/ README.md LICENSE .gitignore .env.example
git commit -m "chore: scaffold — spec, plan, agent instructions"
```

- [x] **Step 2: Write `pyproject.toml`**

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

- [x] **Step 3: Create the package and shared fixtures**

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

- [x] **Step 4: Verify install + empty test run**

Run: `uv venv && uv pip install -e ".[dev]" && .venv/bin/pytest`
Expected: `no tests ran` (exit code 5 is fine at this point).

- [x] **Step 5: Commit**

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
  `narration`, `deepen`, `embedding`, `knowledge_graph`, `concepts`, `okf`, `prompts` —
  `okf` is kept: upstream `AppConfig` carries an `okf` slot and the model-defaults table
  below retunes `OKFConfig.model`). Both `@lru_cache`'d, exactly as upstream.

- [x] **Step 0: Verify GPT-5.6 API model IDs (one manual check, before any code)** —
  **LIVE, not run in the reference build**

Run: `curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['data'] if '5.6' in m['id'] or 'embedding' in m['id']])"`
Expected: IDs containing `gpt-5.6` tiers and `text-embedding-3-small`. If the tier slugs
differ from `gpt-5.6-terra` / `gpt-5.6-luna`, use the real IDs in every step below and in
`config.yaml`, and note the substitution in the commit message.

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codex8.core'`

- [x] **Step 3: Port config.py**

```bash
mkdir -p codex8/core && touch codex8/core/__init__.py
cp _upstream/delapan/core/config.py codex8/core/config.py
```

Then edit `codex8/core/config.py`:

1. Replace every `delapan` string/identifier: imports `delapan.` → `codex8.`, env prefix
   `DLP_` → `C8_`, `DELAPAN_CONFIG_FILE` → `CODEX8_CONFIG_FILE`, docstring product name.
   **Docstring caveat — do NOT rename the override examples mechanically:** the upstream
   module docstring's example is `DLP_AGENT__TEMPERATURE=0.4`, but the `agent` section is
   deleted in this port, so a mechanical rename would advertise a nonexistent section.
   Swap the examples to `C8_TIERS__RICH_HIT_COUNT=7` and `C8_SEARCH__MIN_SIMILARITY=0.2`.
2. Replace the entire `Settings` class body's fields with the single-key surface (keep
   `model_config`, adapting `env_file` resolution as upstream does):

```python
class Settings(BaseSettings):
    """Secrets + deployment identity. One credential: the OpenAI API key."""

    openai_api_key: str | None = None
    codex8_db_path: str | None = None
```

   This full replace deletes every upstream field, explicitly including — beyond the
   obvious gateway/tavily/supabase/anthropic credential fields — `delapan_backend`,
   `delapan_db_path`, `database_url`, `api_key_prefix_live` / `api_key_prefix_test`,
   `mcp_user_email` / `mcp_user_password`, and the `cors_origins` field together with its
   `_parse_cors_origins` validator.
3. Delete `AgentConfig` and `UserProfileConfig` classes and their slots on `AppConfig`
   (the chat agent and profile injection are not ported — SPEC scope cuts). Keep
   `OKFConfig` and the `okf` slot.
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

   Comment caveat on `SynopsisConfig.model`: upstream's trailing comment is
   `# fast model (fills the unused fast_model slot)`, which references
   `AgentConfig.fast_model` — a class this task deletes. Replace the comment with
   `# cheap/fast tier`.

5. Add to `ExplorationConfig` (used by Task 4's researcher):

```python
    research_model: str = "gpt-5.6-luna"  # drives the hosted web_search tool
```

6. Update the comments that say models are "routed through Vercel AI Gateway" to say
   "OpenAI API model IDs".

- [x] **Step 4: Write `config.yaml`** — port the key set of `_upstream/config.yaml`
  **exactly** (same knobs, minus the `agent:` and `user_profile:` sections), all model
  values matching the table above, and the header comment explaining
  `C8_<SECTION>__<FIELD>` overrides (use the two examples from Step 3.1). Do NOT invent
  yaml keys for code-only defaults: upstream's yaml has **no**
  `exploration.evaluation_model`, `exploration.enable_evaluation`, or
  `exploration.max_concurrent_searches` keys — `evaluation_model = "gpt-5.6-terra"` and
  `enable_evaluation = True` exist only as `ExplorationConfig` code defaults.

- [x] **Step 5: Run to green**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 3 passed.

- [x] **Step 6: Commit**

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
  upstream `ai_gateway` (later tasks' ported modules import them by these names; note
  `text_completion` has a keyword-only REQUIRED `system` param — Task 6 relies on this),
  and `embeddings.embed_text(text) -> list[float]`, `embed_batch(texts) -> list[list[float]]`,
  `embed_with_retry(text, retries=2) -> list[float]`.

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codex8.core.clients'`

- [x] **Step 3: Port both modules**

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

- [x] **Step 4: Run to green** — `.venv/bin/pytest tests/test_clients.py -v` → 2 passed.

- [x] **Step 5: Commit**

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
  import-only. **Failure contract (adversarial-review fix, ref commit c41b09c):**
  `search()` also honors upstream `tavily.search`'s never-raise contract — it retries
  with exponential backoff (`@_with_retry(max_retries=3, base_delay=1.0, fallback=list)`,
  ported verbatim from `_upstream/delapan/core/clients/tavily.py`) and returns `[]` once
  exhausted, because the engine gathers queries with no error handling and a single
  raised transient API error would abort the whole exploration.

Both code blocks below are the ruff-formatted versions verified in the reference build —
`ruff format --check` passes on them as written (the earlier draft's `results.append({...})`
one-liner and the test's list-comprehension/assert lines exceeded formatter width).

- [ ] **Step 1: Write the failing test**

`tests/test_research.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import codex8.core.clients.research as research


def _fake_response(text: str, citations: list[tuple[str, str]]):
    annotations = [SimpleNamespace(type="url_citation", url=u, title=t) for u, t in citations]
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
    assert results == [
        {"url": "https://a.example/one", "title": "One", "content": "Summary of results."}
    ]
    assert create.call_args.kwargs["tools"] == [{"type": "web_search"}]


async def test_search_returns_empty_after_exhausted_retries(monkeypatch):
    """Upstream tavily.search contract: a persistently failing query degrades to []
    (never raises) — the engine gathers queries with no error handling, so an
    exception here would abort the whole exploration instead of dropping one query."""
    create = AsyncMock(side_effect=RuntimeError("429 rate limited"))
    monkeypatch.setattr(
        research, "_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(research.asyncio, "sleep", fake_sleep)
    results = await research.search("test query", max_results=3, search_depth="basic")
    assert results == []
    assert create.await_count == 4  # 1 attempt + 3 retries
    assert sleeps == [1.0, 2.0, 4.0]  # exponential backoff, no sleep after the last attempt


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
import functools
import logging
from html.parser import HTMLParser
from io import StringIO
from typing import Any, Awaitable, Callable

import httpx
from openai import AsyncOpenAI

from codex8.core.config import get_config, get_settings

logger = logging.getLogger(__name__)

_MAX_PAGE_CHARS = 40_000
_FETCH_TIMEOUT = 20.0


def _with_retry(max_retries: int, base_delay: float, fallback: Callable[[], Any]):
    """Async exponential-backoff retry. Returns ``fallback()`` once exhausted."""

    def decorator(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 — transport/provider errors
                    last_exc = exc
                    if attempt < max_retries:
                        await asyncio.sleep(base_delay * (2**attempt))
            logger.warning("%s exhausted retries: %s", func.__name__, last_exc)
            return fallback()

        return wrapper

    return decorator


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


@_with_retry(max_retries=3, base_delay=1.0, fallback=list)
async def search(query: str, *, max_results: int, search_depth: str = "basic") -> list[dict]:
    """Hosted web_search; returns [{url, title, content}] like Tavily's search
    ([] on failure — the engine gathers queries with no error handling, so one
    failed query must degrade to no results, never abort the exploration).

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
                    results.append(
                        {"url": url, "title": getattr(ann, "title", url), "content": text}
                    )
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

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_research.py -v` → 3 passed.

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

**LIVE, not run in the reference build.** Run it once with a real key:
`.venv/bin/python scripts/smoke_research.py "sqlite-vec"`.
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
- Produces: `get_store(access_token: str | None = None, *, org_id: str | None = None) -> Store`
  — the exact upstream signature; both args are accepted for upstream call-site parity
  and ignored on the local tier; always returns a cached `SQLiteStore` (the supabase
  branch is deleted). Also `active_backend() -> str`, **kept and hardwired to
  `"local"`** — upstream `mcp/tenancy.py` (ported in Task 9) does
  `from delapan.store import active_backend, get_store`, so this seam must survive; it
  also lets a future cloud tier slot back in without touching call sites.
- Store surface used later (verified upstream signatures — write tests against these):
  `resolve_project(name, *, create: bool) -> tuple[str, str]` (returns
  `(org_id, project_id)`; `create` is a required keyword),
  `resolve_kb(org_id, project_id, name, *, create: bool) -> str`,
  `match_findings(kb_id, query_embedding, match_count, min_similarity, categories=None)`
  (no `limit` kwarg; `min_similarity` required), `insert_findings`,
  `create_exploration`, synopsis read/write, KG node/edge upserts.

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: codex8.store`.

- [ ] **Step 3: Port the three files**

```bash
mkdir -p codex8/store
cp _upstream/delapan/store/base.py codex8/store/base.py
cp _upstream/delapan/store/sqlite.py codex8/store/sqlite.py
cp _upstream/delapan/store/__init__.py codex8/store/__init__.py
```

Edits:

- Rename imports `delapan.*` → `codex8.*` (sweep docstrings too — upstream `base.py`
  carries `delapan` in its module docstring and a `delapan_mark_init_offered` mention).
- Default DB path `~/.delapan/delapan.db` → `~/.codex8/codex8.db`. `_default_db_path()`
  checks the process env first (`CODEX8_DB_PATH` — test-friendly, no cache), then a
  **resilient** `Settings.codex8_db_path` fallback: import `get_settings` inside a
  `try/except Exception` so the store stays importable without `codex8.core.config`,
  and so a monkeypatched env var beats the `lru_cache`'d Settings. Upstream reads only
  the env — the Settings fallback is a deliberate codex8 addition.
- In `__init__.py`'s `get_store`: delete the supabase/cloud branch and its lazy import,
  delete `_has_cloud_creds()` and the `DELAPAN_BACKEND` env sniff, so it returns a
  cached `SQLiteStore` unconditionally (module-level singleton keyed by db_path — one
  connection reused; a different `CODEX8_DB_PATH`, as tests use, gets its own store).
  **Keep `active_backend()`**, reduced to `return "local"` (see Interfaces). Delete
  `store/supabase.py` references.
- Schema DDL, `vec0 float[1536]` tables, and cosine KNN SQL stay byte-identical — with
  one whitespace exception: upstream `sqlite.py` fails `ruff format --check` (missing
  two blank lines between `_finding_from_row` and `_FINDING_MATCH_COLS`). Run
  `.venv/bin/ruff format codex8/store/sqlite.py` after the port; the diff is
  whitespace-only, DDL and SQL untouched.

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
- Produces: `select_preamble(query, *, store, kb_id, depth) -> tuple[str, Coverage]` —
  the verified upstream signature: positional query, keyword-only rest, returns the
  `(xml, coverage)` tuple that `mcp/server.py` tuple-unpacks. Also
  `maybe_rebuild_synopsis(...)`, `load_synopsis(...)`, and `TenantContext` — a dataclass
  with **six required fields**: `user_id`, `org_id`, `project_id`, `kb_id`, `thread_id`
  (no default — upstream tenancy passes `str(uuid.uuid4())`), `access_token`.

- [ ] **Step 1: Write the failing test**

`tests/test_agent.py`:

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import codex8.core.agent.preamble as preamble_mod
import codex8.core.agent.synopsis as synopsis_mod
from codex8.core.agent.preamble import select_preamble
from codex8.core.agent.state import TenantContext
from codex8.core.agent.synopsis import load_synopsis, maybe_rebuild_synopsis
from codex8.store.sqlite import SQLiteStore


def _kb(store: SQLiteStore) -> str:
    org_id, project_id = store.resolve_project("p", create=True)
    return store.resolve_kb(org_id, project_id, "kb", create=True)


async def test_preamble_coverage_gap_on_empty_kb(tmp_path, monkeypatch, fake_embedding):
    monkeypatch.setattr(preamble_mod, "embed_text", AsyncMock(return_value=fake_embedding))
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = _kb(s)
    xml, coverage = await select_preamble("anything", store=s, kb_id=kb_id, depth="normal")
    assert coverage == "gap"
    assert "<preamble>" in xml


def test_tenant_context_shape():
    ctx = TenantContext(
        user_id="local",
        org_id="local",
        project_id="x",
        kb_id="y",
        thread_id="t",
        access_token="",
    )
    assert ctx.org_id == "local"


async def test_synopsis_rebuild_uses_text_completion(tmp_path, monkeypatch, fake_embedding):
    entries = [{"topic": "sqlite", "gloss": "The KB knows about sqlite-vec storage."}]
    fake_llm = AsyncMock(return_value=json.dumps(entries))
    monkeypatch.setattr(synopsis_mod, "text_completion", fake_llm)
    s = SQLiteStore(db_path=str(tmp_path / "t.db"))
    kb_id = _kb(s)
    await s.insert_findings(
        [
            {
                "kb_id": kb_id,
                "title": "sqlite-vec",
                "content": "vec0 tables",
                "category": "fact",
                "confidence": 0.9,
                "embedding": fake_embedding,
            }
        ]
    )
    await maybe_rebuild_synopsis(kb_id, store=s)
    fake_llm.assert_awaited_once()
    assert "model" in fake_llm.await_args.kwargs
    row = load_synopsis(s, kb_id)
    assert row is not None
    assert row["content"] == entries
```

The third test exists because the `synopsis.py` LLM-call rewrite (Step 3) is this task's
only hand-written seam — the first two tests never exercise it. It runs
`maybe_rebuild_synopsis` end-to-end against a real tmp SQLiteStore with only the LLM
mocked, and asserts `load_synopsis` returns the parsed entries.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the four modules**

```bash
mkdir -p codex8/core/agent && touch codex8/core/agent/__init__.py
for f in state synopsis preamble concept_doc; do
  cp "_upstream/delapan/core/agent/$f.py" "codex8/core/agent/$f.py"
done
```

Edits — all files: rename imports `delapan.*` → `codex8.*` and
`clients.ai_gateway` → `clients.openai_client`. `state.py` ports unchanged otherwise
(keep `thread_id` required). Then the one real seam, in `synopsis.py`: it imports
`from delapan.core.clients.anthropic import chat_model`. Delete that import and rewrite
its single LLM call site (`_build`) to use
`from codex8.core.clients.openai_client import text_completion`. Two verified details:

- `text_completion`'s `system` param is keyword-only and REQUIRED, but the upstream
  `_build` sent its entire prompt as one user message (`llm.ainvoke([{role: user, ...}])`)
  with no system prompt. Preserve that behavior with an explicit empty system:

```python
    text = await text_completion(
        model=cfg.model,
        system="",  # upstream sent the whole prompt as one user message; keep it verbatim
        user=_build_prompt(findings, cfg),
    )
```

- Drop the now-dead `isinstance(resp.content, str)` guard — `text_completion` returns
  `str` directly. Prompt strings stay verbatim.

- [ ] **Step 4: Run to green** — `.venv/bin/pytest tests/test_agent.py -v` → 3 passed.

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

`tests/test_exploration.py` — the mock shapes below are the verified ones:
`structured_completion` returns **pydantic instances**, not raw dicts. `plan_queries`
passes `response_format=ExplorationPlan` and the engine dereferences
`plan.search_queries[*].query`, `plan.extraction_prompt`, `plan.expected_categories`,
`plan.finding_title_hint` (a dict raises `AttributeError` immediately); `extract_findings`
passes `response_format=FindingBatch` and does `batch.findings` →
`f.model_dump(exclude_none=True)`. The **evaluator must also be mocked**:
`run_exploration` awaits `evaluate_findings`, which makes a `structured_completion` call
whenever `cfg.enable_evaluation` is True — the built-in default, and `config.yaml` does
not disable it. Narrator needs no mock (`_narrated` short-circuits when `on_narration`
is None, which this test never passes); merger and deepen make no LLM calls on this path.

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.core.exploration.engine as engine_mod
import codex8.core.exploration.evaluator as evaluator_mod
import codex8.core.exploration.extractor as extractor_mod
import codex8.core.exploration.planner as planner_mod
from codex8.core.exploration.models import (
    ExplorationPlan,
    FindingBatch,
    RawFinding,
    SearchQuery,
)


async def test_engine_uses_research_not_tavily():
    assert not hasattr(engine_mod, "tavily")
    assert hasattr(engine_mod, "research")


async def test_run_exploration_smoke(monkeypatch):
    from codex8.core.config import get_config
    from codex8.core.exploration import run_exploration

    monkeypatch.setattr(
        engine_mod.research,
        "search",
        AsyncMock(
            return_value=[{"url": "https://x.example/a", "title": "A", "content": "snippet"}]
        ),
    )
    monkeypatch.setattr(
        engine_mod.research,
        "extract",
        AsyncMock(return_value={"https://x.example/a": "Full page text about the topic."}),
    )
    # Plan / extract / evaluate LLM calls: mock structured_completion at each
    # consumer module, returning the parsed pydantic shape each one expects.
    # Narration never fires (no on_narration callback is passed below).
    monkeypatch.setattr(
        planner_mod,
        "structured_completion",
        AsyncMock(
            return_value=ExplorationPlan(
                search_queries=[SearchQuery(query="q1")],
                extraction_prompt="Extract concrete facts.",
                expected_categories=["c"],
                finding_title_hint="{fact}",
            )
        ),
    )
    monkeypatch.setattr(
        extractor_mod,
        "structured_completion",
        AsyncMock(
            return_value=FindingBatch(
                findings=[RawFinding(title="F1", content={"fact": "x"}, category="c")]
            )
        ),
    )
    monkeypatch.setattr(
        evaluator_mod,
        "structured_completion",
        AsyncMock(
            return_value=evaluator_mod._EvaluationBatch(
                verdicts=[evaluator_mod._FindingVerdict(index=0, quality=0.9, keep=True)]
            )
        ),
    )

    findings = await run_exploration(
        "topic",
        exploration_id="e1",
        project_id="p1",
        kb_id="k1",
        cfg=get_config().exploration,
    )
    assert findings
    f = findings[0]
    assert f.title == "F1"
    assert f.provenance == [{"url": "https://x.example/a", "query": "q1"}]
    # merger: 1 source (0.4) × critic quality 0.9 → blended confidence 0.36
    assert abs(f.confidence - 0.36) < 1e-9
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port all nine files** (the `Files` line and the loop below list nine:
  `__init__` plus eight modules)

```bash
mkdir -p codex8/core/exploration
for f in __init__ models planner extractor merger evaluator narrator deepen engine; do
  cp "_upstream/delapan/core/exploration/$f.py" "codex8/core/exploration/$f.py"
done
```

Edits — all files: `delapan.*` → `codex8.*`, `clients.ai_gateway` → `clients.openai_client`.
In `engine.py` only: `from codex8.core.clients import research` replaces
`from delapan.core.clients import tavily`, then `tavily.search(` → `research.search(` and
`tavily.extract(` → `research.extract(`. One formatting consequence: the upstream
`tavily.extract` call line is exactly 100 chars, and "research" is 2 chars longer, so the
mechanical swap breaks ruff line-length 100 — wrap the call as the reference build did:

```python
        content_by_url = await research.extract(
            urls[: cfg.max_pages], search_depth=cfg.search_depth
        )
```

Nothing else changes (the Task 4 surface is signature-compatible). Run
`.venv/bin/ruff format --check codex8/core/exploration/` before committing.

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

`tests/test_knowledge_graph.py` — the cross-task import check uses a `find_spec` skip so
this file is green even if the agent package (Task 6) has not landed (out-of-order or
concurrent execution); it auto-activates and genuinely imports once Task 6 exists, so kg
failures are never masked:

```python
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
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the six modules** (same copy+rename recipe — `delapan.*` → `codex8.*`,
  `ai_gateway` → `openai_client`) with two verified seams beyond imports:

  1. **`builder.py` — decouple from the agent package.** Upstream does a module-level
     `from delapan.core.agent.state import TenantContext`, but `TenantContext` is
     annotation-only in builder (postponed annotations + attribute access). Move it under
     `if TYPE_CHECKING:` — the same pattern upstream `extractor.py` already uses for
     `KGSchema`. Runtime behavior is unchanged, and the kg package imports cleanly even
     when `codex8/core/agent/` is absent:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codex8.core.agent.state import TenantContext
```

  2. **Product-name docstring seams** — imports-only would leave stale references:
     `__init__.py` names `/v1/graph` + `delapan_graph` (→ `codex8_graph`) and "Supabase
     persistence" (→ Store); `extractor.py`'s flow diagram says "AI Gateway" / "routes
     through the gateway" (→ "OpenAI API"); `models.py` says "see CLAUDE.md" (→ "see
     AGENTS.md"); `service.py`'s `render_kg_context` emits the user-facing string
     "run `delapan_build_graph`" (→ "run `codex8_build_graph`"). **Caveat:**
     `codex8_graph` / `codex8_build_graph` name tools NOT in codex8's ported MCP surface
     (resume/search/explore/projects only) — `render_kg_context` currently has no ported
     caller, so this wording is a canonical placeholder for a future graph tool, not a
     live tool name. Do NOT sweep upstream's own provenance phrases ("Ported from
     delapan", "Mirrors delapan's guard") — they are factual lineage; a blind
     `delapan` → `codex8` sweep corrupts them.

- [ ] **Step 4: Run the FULL suite to green** — `.venv/bin/pytest -v`. Executed in order,
  this is the first point where every `codex8.core` package must import cleanly together.
  (If tasks ran out of order and Task 6 has not landed, the `find_spec` test above skips
  and re-activates on the first full-suite pass after the agent package exists — verify
  this task standalone with its own test file plus explicit imports of all six kg
  modules.)

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
- Verified upstream behaviors the tests below encode: resume/search resolve with
  `resolve_tenant(..., create=False)` and return `{"error": "KB not found..."}` for a
  missing project/KB — **resume never creates**; only `codex8_explore` uses
  `create=True`. And resume never triggers a synopsis rebuild: only the explore tool
  calls `maybe_rebuild_synopsis` (after persisting findings); `select_preamble` does a
  pure store read via `load_synopsis`, so no synopsis mock is needed.

- [ ] **Step 1: Write the failing test**

`tests/test_mcp_server.py` — two verified test-shape corrections baked in: (1) the
resume path embeds through `codex8.core.agent.preamble`'s own module-level `embed_text`
binding, so patch **there**, not on the server module (`server.embed_text` only feeds
`codex8_search`); (2) because resume uses `create=False`, seed the project/KB first via
`server.resolve_tenant("p", "k", create=True)`:

```python
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
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Port the four modules**

```bash
mkdir -p codex8/mcp
for f in __init__ server tenancy banner; do cp "_upstream/delapan/mcp/$f.py" "codex8/mcp/$f.py"; done
```

Edits: rename imports; rename the four tool functions `delapan_*` → `codex8_*` (decorator
and docstrings included); in `tenancy.py` delete the cloud branch (`_login`,
`_service_client`, `_org_for`, and the `active_backend()` fork) so `resolve_tenant` /
`resolve_store` always take the local path (`org_id="local"`, empty token) — the store's
`active_backend()` seam kept in Task 5 means the upstream import keeps resolving while
you edit; keep `resolve_tenant`'s `create: bool = True` keyword and the
`thread_id=str(uuid.uuid4())` it passes into `TenantContext`. In `banner.py` swap the
wordmark text to `c o d e x 8` keeping the layout. Server name string in the FastMCP
constructor → `"codex8"`.

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
- Test: `tests/test_plugin_shell.py`

**Interfaces:**
- Consumes: tool names from Task 9.
- Produces: a Codex-discoverable plugin — `[mcp_servers.codex8]` in `~/.codex/config.toml`
  plus skills under `~/.codex/skills/codex8-*`.

- [ ] **Step 1: Write the four skills.** Frontmatter format: `name` + `description`.
  Content pattern (write all four; `resume` shown in full). Note: this short
  Codex-flavored template is a **deliberate divergence** from upstream's richer SKILL.md
  shape (Target-resolution bash block, Workflow, When-to-use sections) — the skills are a
  new plugin-shell seam, not a byte-faithful port. In particular, upstream's resume skill
  instructs the model to render an observability banner template itself; codex8's server
  returns a ready-made `banner` field, so the skill just leads with it.

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

- [ ] **Step 3: Write `tests/test_plugin_shell.py`** — the plan preamble mandates a
  failing-test-first cycle per task; this file is the shell's automated check (skill
  frontmatter/tool-name assertions + installer register/idempotency/symlink assertions,
  driven through a subprocess with `CODEX_HOME` pointed at `tmp_path`):

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = ("resume", "search", "explore", "projects")


def test_skills_have_frontmatter_and_name_the_mcp_tool():
    for s in SKILLS:
        text = (REPO / "skills" / s / "SKILL.md").read_text()
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert f"name: codex8-{s}" in frontmatter
        assert "description:" in frontmatter
        assert f"codex8_{s}" in text  # each skill names its MCP tool


def _install(codex_home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO / "install.sh")],
        env={**os.environ, "CODEX_HOME": str(codex_home)},
        capture_output=True,
        text=True,
        check=True,
    )


def test_installer_registers_server_and_links_skills(tmp_path):
    out = _install(tmp_path)
    assert "registered [mcp_servers.codex8]" in out.stdout
    config = (tmp_path / "config.toml").read_text()
    assert config.count("[mcp_servers.codex8]") == 1
    assert f'command = "{REPO}/.venv/bin/python"' in config
    assert '"codex8.mcp.server"' in config
    for s in SKILLS:
        link = tmp_path / "skills" / f"codex8-{s}"
        assert link.is_symlink()
        assert link.resolve() == (REPO / "skills" / s).resolve()


def test_installer_is_idempotent(tmp_path):
    _install(tmp_path)
    second = _install(tmp_path)
    assert "leaving it untouched" in second.stdout
    config = (tmp_path / "config.toml").read_text()
    assert config.count("[mcp_servers.codex8]") == 1
```

- [ ] **Step 4: Verify — hermetic idempotency check** (never against the real `~/.codex`;
  `install.sh` honors the `CODEX_HOME` override)

Run:

```bash
chmod +x install.sh && bash -n install.sh
.venv/bin/pytest tests/test_plugin_shell.py -v
C8_TMP=$(mktemp -d) && CODEX_HOME="$C8_TMP" ./install.sh && CODEX_HOME="$C8_TMP" ./install.sh
grep -c 'mcp_servers.codex8' "$C8_TMP/config.toml" && rm -rf "$C8_TMP"
```

Expected: 3 tests passed; second run prints "already has … leaving it untouched"; grep
count = 1. (This task ships no new Python module, so the per-task import anchor is just
`python -c "import codex8"` plus the `bash -n` syntax check above.)

- [ ] **Step 5: Live plugin check** — **LIVE, not run in the reference build.** Run
  `./install.sh` for real (this time against the real `~/.codex`), open a NEW Codex
  session in any folder, and confirm the `codex8_projects` tool is callable and skills
  appear. This is the Phase 2 gate.

- [ ] **Step 6: Commit**

```bash
git add skills/ install.sh tests/test_plugin_shell.py
git commit -m "feat: Codex plugin shell — skills + config.toml installer"
```

### Task 11: Demo KB — judge path without exploration

**Files:**
- Create: `scripts/seed_demo.py`, `data/demo.db` (built artifact, committed — LIVE step),
  `data/demo_findings.json` (source of truth, committed)
- Test: `tests/test_demo_seed.py`

**Interfaces:**
- Consumes: store (Task 5), embeddings (Task 3).
- Produces: a committed KB (`project="codex8-demo"`, `kb="build-week"`) so judges get
  ranked recall for the cost of one query-embedding call — no exploration required.

- [ ] **Step 1: Author `data/demo_findings.json`** — 15–25 findings about codex8 itself
  and OpenAI Build Week. Write them by hand from `SPEC.md` and the hackathon rules; this
  doubles as the demo script's material. Each finding carries the **real
  `insert_findings` row shape** (mirroring the server's explore persist path) minus the
  three keys the seed script adds:

```json
{
  "title": "…",
  "content": "… (markdown STRING, not an object)",
  "category": "…",
  "confidence": 1.0,
  "tags": ["…"],
  "provenance": [{"url": "…"}]
}
```

  `confidence` is a float, `tags` a list, `provenance` a list of `{url, ...}` dicts. The
  seed adds `org_id`, `kb_id`, and `embedding` per row; `tests/test_demo_seed.py` (Step 3)
  locks this schema.

- [ ] **Step 2: Write `scripts/seed_demo.py`** — the seeding logic is an importable
  `seed(db_path, findings_path=FINDINGS_PATH)` coroutine, NOT module-scope
  `asyncio.run(...)`: the unit test imports this module and runs `seed()` against a
  `tmp_path` db with `embed_batch` monkeypatched, so top-level execution would hit the
  network on import. Execution is guarded by `if __name__ == "__main__":`. (Two more
  verified details: `store.close()` checkpoints WAL so the committed `.db` is a single
  file, and the docstring's unindented trailing paragraph keeps the ASCII diagram's
  4-space indent intact under `ruff format` — a diagram that is the only continuation
  line gets dedented.) The script also upserts a hand-authored `SYNOPSIS` constant
  (ref commit 119c0e3) because a keyless `codex8_resume(query=None)` never embeds and
  would otherwise render `<empty/>` on a KB with no synopsis row — the synopsis spine IS
  the judge's entire no-query resume payload.

```python
"""Build data/demo.db from data/demo_findings.json — run once with OPENAI_API_KEY set.

    demo_findings.json ──► embed_batch ──► SQLiteStore(data/demo.db) ──► committed artifact

The committed demo KB (project ``codex8-demo``, kb ``build-week``) gives judges
ranked recall for the cost of one query-embedding call — no exploration needed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from codex8.core.clients.embeddings import embed_batch
from codex8.store.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_PATH = ROOT / "data" / "demo_findings.json"
DB_PATH = ROOT / "data" / "demo.db"

# Hand-authored synopsis spine ({topic, gloss} entries, same shape agent/synopsis._build
# produces) so a keyless `codex8_resume` on the demo KB renders a real <synopsis> instead
# of <empty/> — resume with no query never embeds, so this is the whole keyless payload.
SYNOPSIS = [
    {
        "topic": "codex8 plugin",
        "gloss": (
            "A hard fork of the delapan knowledge engine ported to Codex: GPT-5.6 is the "
            "only agent, OPENAI_API_KEY the only credential, SQLite + sqlite-vec the only store."
        ),
    },
    {
        "topic": "MCP surface",
        "gloss": (
            "Four stdio tools — codex8_resume, codex8_search, codex8_explore, codex8_projects — "
            "registered via [mcp_servers.codex8] in ~/.codex/config.toml by install.sh."
        ),
    },
    {
        "topic": "exploration pipeline",
        "gloss": (
            "plan -> search -> crawl -> extract -> merge on GPT-5.6; the hosted web_search tool "
            "replaces Tavily and findings embed with text-embedding-3-small at 1536 dims."
        ),
    },
    {
        "topic": "OpenAI Build Week",
        "gloss": (
            "Devpost hackathon, Developer Tools track; submissions due 2026-07-21 17:00 PDT and "
            "judged on Codex leverage, design, potential impact, and quality of the idea."
        ),
    },
    {
        "topic": "judge quick-path",
        "gloss": (
            "CODEX8_DB_PATH=data/demo.db exposes this pre-seeded KB (project codex8-demo, kb "
            "build-week); resume/search work immediately, only codex8_explore spends real research."
        ),
    },
    {
        "topic": "evidence discipline",
        "gloss": (
            "The port is built in one primary Codex thread (session ID via /feedback); "
            "_upstream/ is the frozen prior-work snapshot, never edited."
        ),
    },
]


async def seed(db_path: Path, findings_path: Path = FINDINGS_PATH) -> list[str]:
    """Embed the demo findings and insert them into a fresh `codex8-demo`/`build-week` KB."""
    findings = json.loads(findings_path.read_text())
    db_path.unlink(missing_ok=True)
    store = SQLiteStore(db_path=str(db_path))
    org_id, project_id = store.resolve_project("codex8-demo", create=True)
    kb_id = store.resolve_kb(org_id, project_id, "build-week", create=True)
    vecs = await embed_batch([f["content"] for f in findings])
    rows = [
        {**f, "org_id": org_id, "kb_id": kb_id, "embedding": v}
        for f, v in zip(findings, vecs, strict=True)
    ]
    ids = await store.insert_findings(rows)
    store.upsert_synopsis(kb_id, SYNOPSIS, len(ids), "hand-authored")
    store.close()  # checkpoints WAL so the committed .db is a single file
    return ids


async def main() -> None:
    ids = await seed(DB_PATH)
    print(f"seeded {len(ids)} findings into {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Write `tests/test_demo_seed.py`** — three tests: locks the findings
  schema; asserts the committed `data/demo.db` artifact resolves on a fresh clone AND
  that a keyless resume (`select_preamble(None, ...)`) renders the `<synopsis>` spine
  with coverage `"gap"` (the honest no-query verdict) rather than `<empty/>`; and proves
  `codex8_search`-level recall (the exact `match_findings` call the search tool makes)
  with no network — `embed_batch` is monkeypatched to distinct one-hot vectors so
  querying with `_one_hot(i)` must recall finding `i` first:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from codex8.store.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


def _load_seed_demo():
    """Import scripts/seed_demo.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("seed_demo", ROOT / "scripts" / "seed_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one_hot(i: int) -> list[float]:
    v = [0.0] * 1536
    v[i] = 1.0
    return v


def test_demo_findings_shape():
    """The committed source of truth matches the real insert_findings row shape."""
    findings = json.loads((ROOT / "data" / "demo_findings.json").read_text())
    assert 15 <= len(findings) <= 25
    for f in findings:
        assert f["title"] and isinstance(f["title"], str)
        assert f["content"] and isinstance(f["content"], str)
        assert f["category"] and isinstance(f["category"], str)
        assert isinstance(f["confidence"], float)
        assert isinstance(f["tags"], list)
        assert f["provenance"] and all("url" in p for p in f["provenance"])


async def test_committed_demo_db_is_shipped_and_resolvable(tmp_path):
    """SPEC constraint 4: data/demo.db is a committed artifact — the judge quick-path
    (CODEX8_DB_PATH=data/demo.db, project codex8-demo, kb build-week) must resolve on
    a fresh clone with no seeding run. Reads a copy so the artifact stays pristine."""
    src = ROOT / "data" / "demo.db"
    assert src.exists(), "data/demo.db must be committed (judge quick-path)"
    db = tmp_path / "demo.db"
    db.write_bytes(src.read_bytes())

    findings = json.loads((ROOT / "data" / "demo_findings.json").read_text())
    store = SQLiteStore(db_path=str(db))
    org_id, project_id = store.resolve_project("codex8-demo", create=False)
    kb_id = store.resolve_kb(org_id, project_id, "build-week", create=False)
    # min_similarity=-1.0 keeps every row regardless of the probe vector's angle.
    hits = await store.match_findings(kb_id, _one_hot(0), match_count=50, min_similarity=-1.0)
    assert len(hits) == len(findings)

    # Keyless resume payload: query=None never embeds, so the synopsis spine IS the
    # judge's first impression — it must render, not <empty/>.
    from codex8.core.agent.preamble import select_preamble

    xml, coverage = await select_preamble(None, store=store, kb_id=kb_id, depth="normal")
    assert "<synopsis>" in xml and "codex8 plugin" in xml
    assert coverage == "gap"  # no query -> no bands; gap is the honest no-query verdict
    store.close()


async def test_seed_then_search_recall(tmp_path, monkeypatch):
    """Seeding logic + codex8_search-level recall (store.match_findings) on a tmp db."""
    seed_demo = _load_seed_demo()
    findings = json.loads(seed_demo.FINDINGS_PATH.read_text())

    async def fake_embed_batch(texts):
        # Distinct orthogonal vectors: querying with _one_hot(i) must recall finding i.
        return [_one_hot(i) for i in range(len(texts))]

    monkeypatch.setattr(seed_demo, "embed_batch", fake_embed_batch)
    db = tmp_path / "demo.db"
    ids = await seed_demo.seed(db)
    assert len(ids) == len(findings)

    store = SQLiteStore(db_path=str(db))
    org_id, project_id = store.resolve_project("codex8-demo", create=False)
    kb_id = store.resolve_kb(org_id, project_id, "build-week", create=False)
    # Same call codex8_search makes: match_count=limit or 10, min_similarity=0.0.
    target = 3
    hits = await store.match_findings(kb_id, _one_hot(target), match_count=10, min_similarity=0.0)
    assert hits, "expected ranked findings"
    assert hits[0]["title"] == findings[target]["title"]
    assert hits[0]["similarity"] > 0.99
    assert set(hits[0]) == {
        "id",
        "title",
        "content",
        "category",
        "confidence",
        "tags",
        "provenance",
        "similarity",
    }
    store.close()
```

Run: `.venv/bin/pytest tests/test_demo_seed.py -v`
Expected: 2 passed, 1 failed — `test_committed_demo_db_is_shipped_and_resolvable` is the
failing test that Step 4 turns green (it asserts `data/demo.db` exists, which the LIVE
build below produces). This IS the task's failing-test-first cycle.

- [ ] **Step 4: Build and verify** — **LIVE: this repo must build its own `data/demo.db`
  with the operator's real `OPENAI_API_KEY`** (the reference build ships one, but the
  judged repo's artifact must be embedded and committed here, not copied).

Run: `.venv/bin/python scripts/seed_demo.py` then
`CODEX8_DB_PATH=data/demo.db .venv/bin/python -c "import asyncio; from codex8.mcp.server import codex8_search; print(asyncio.run(codex8_search(project='codex8-demo', kb='build-week', query='what is codex8')))"`
Expected: ranked findings with similarities. Then re-run
`.venv/bin/pytest tests/test_demo_seed.py -v` → 3 passed.

- [ ] **Step 5: Commit** (yes, the .db is committed — it IS the judge sandbox)

```bash
git add scripts/seed_demo.py data/ tests/test_demo_seed.py
git commit -m "feat: pre-seeded demo KB — judge path with zero exploration cost"
```

---

## Phase 3 — Submission polish

### Task 12: E2E verification, README, evidence capture

**Files:**
- Modify: `README.md` (replace stub sections)

- [ ] **Step 1: Full-suite + lint gate** — `.venv/bin/pytest && .venv/bin/ruff check .`
  green (the reference build lands at 26 passed; `ruff format --check .` is also clean).

- [ ] **Step 2: Live E2E in a fresh Codex session** — **LIVE, not run in the reference
  build** (the acceptance criteria from SPEC.md): demo-KB resume + search; then one real
  `codex8_explore` on a novel prompt; then `codex8_resume` again showing the coverage
  upgrade. Screen-record this — it is the demo video's spine.

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
- The first draft's "known unknowns" (store method names, `select_preamble` signature,
  planner/extractor schemas, evaluator involvement, Responses API mock shape) were all
  resolved by the reference execution and are now baked into the tasks as verified
  signatures and code blocks — see "Reference execution" above. The only remaining
  reality checks are the LIVE steps listed there; for those, the original rule stands:
  observe the live API first, adapt to reality, keep the port faithful.
- The stretch differentiator (multi-agent explore) is deliberately NOT a task — it enters
  only if Tasks 1–12 are done and verified before 2026-07-20.
