# codex8 — port spec

**codex8** is a hard fork of the [delapan](https://delapan.ai) knowledge engine, ported to a
**Codex / GPT-5.6 plugin**: GPT-5.6 is the only reasoning model, OpenAI is the only API
dependency, and the plugin surface targets Codex conventions (MCP server in
`~/.codex/config.toml`, `SKILL.md` skills, `AGENTS.md`).

Built for **OpenAI Build Week** (openai.devpost.com), Developer Tools track.
Submission deadline: **Tue 2026-07-21 17:00 PDT**.

```
codex8/                       the ported engine (Python package)
├─ core/
│  ├─ config.py               Settings (.env) + AppConfig (config.yaml); C8_<SECTION>__<FIELD> overrides
│  ├─ clients/
│  │  ├─ openai_client.py     text_completion / structured_completion → api.openai.com (fork of ai_gateway.py)
│  │  ├─ embeddings.py        text-embedding-3-small @ 1536 dims
│  │  └─ research.py          NEW — search() via Responses API web_search; extract() via httpx + stdlib HTML→text
│  ├─ agent/                  preamble, synopsis, state, concept_doc (synopsis: anthropic → openai_client)
│  ├─ exploration/            plan → search → crawl → extract → merge (engine: tavily → research)
│  └─ knowledge_graph/        finding → KG extraction (schedule_kg_update stays in the explore path)
├─ store/                     base.py + sqlite.py ONLY (SQLite + sqlite-vec, org_id="local")
└─ mcp/                       server (codex8_resume/search/explore/projects), tenancy (local tier), banner
skills/                       Codex skills: resume, search, explore, projects (SKILL.md each)
_upstream/delapan/            frozen snapshot of the upstream engine — prior work, never edited
```

## Constraints (competition-derived, non-negotiable)

1. **Single key.** The only credential is `OPENAI_API_KEY`. No Tavily, no Vercel AI Gateway,
   no Supabase, no Anthropic. Judges run it with their own key.
2. **GPT-5.6 everywhere.** Every LLM call routes to GPT-5.6 tiers via the OpenAI API
   (heavy: `gpt-5.6-terra`; cheap/fast: `gpt-5.6-luna` — verify exact API model IDs against
   https://platform.openai.com/docs/models in Phase 0 and adjust `config.yaml` if they differ).
   Embeddings: `text-embedding-3-small` (natively 1536 dims — matches the existing
   `vec0 float[1536]` tables; no schema change).
3. **Local-first.** Storage is SQLite + sqlite-vec at `~/.codex8/codex8.db`. No cloud tier
   in this repo (roadmap item only).
4. **Testable without rebuild.** Ship a pre-seeded demo DB (`data/demo.db`) so
   `codex8_resume` / `codex8_search` work immediately against committed data — no
   exploration cost; a query costs one embedding call on the judge's own key.
5. **Evidence discipline.** All code is written in the primary Codex session. `_upstream/`
   is imported in one clearly-labeled commit and never modified. Small, frequent commits.
   Run `/feedback` in the primary thread at the end to obtain the submission session ID.

## Scope cuts (exist upstream, deliberately NOT ported)

- `api/` (FastAPI `/v1` deploy surface) — judges use the MCP surface via Codex.
- `store/supabase.py`, `clients/supabase.py` (cloud tier), `clients/anthropic.py`,
  `clients/tavily.py` (replaced by `research.py`).
- HTML report generation and the sigma.js frontend.

## Surface (MCP tools, identical semantics to upstream)

| Tool | Does |
|---|---|
| `codex8_resume(project, kb, query?, depth)` | coverage band (`rich`/`sparse`/`gap`) + rendered `<preamble>` |
| `codex8_search(project, kb, query, limit?)` | semantic recall over findings (cosine, sqlite-vec) |
| `codex8_explore(project, kb, prompt, max_findings?)` | web research pipeline → persisted findings (creates project/KB on demand) |
| `codex8_projects()` | list projects/KBs |

## Fork rules (inherited from the br8n playbook)

- Copy files from `_upstream/delapan/`, rename every import `delapan.*` → `codex8.*`.
- Never import from `delapan` or `br8n`. codex8 is fully standalone.
- Env prefix `DLP_` → `C8_`; env file keys reduce to `OPENAI_API_KEY` (+ optional
  `CODEX8_CONFIG_FILE`, `CODEX8_DB_PATH`).
- House style preserved: `from __future__ import annotations`, type hints, terse module
  docstrings with ASCII flow diagrams, ruff line-length 100.

## Acceptance criteria (submission checklist)

- [ ] `uv venv && uv pip install -e ".[dev]" && pytest` green on a fresh clone (macOS + Linux).
- [ ] `./install.sh` wires `[mcp_servers.codex8]` into `~/.codex/config.toml` and links `skills/`.
- [ ] In a fresh Codex session with only `OPENAI_API_KEY` set: `codex8_resume` on the demo
      KB returns a preamble with a coverage band and `codex8_search` returns ranked
      findings — no exploration run needed (one embedding call per query).
- [ ] With `OPENAI_API_KEY`: `codex8_explore` on a novel prompt persists ≥ 5 findings and a
      follow-up `codex8_resume` upgrades coverage.
- [ ] README: install, supported platforms, judge quick-path, "how Codex accelerated the
      workflow" narrative, no API keys anywhere in the repo.
- [ ] Demo video < 3 min, public YouTube. `/feedback` session ID captured.

## Differentiator (stretch, only after acceptance criteria pass)

GPT-5.6's Responses API **multi-agent beta** (concurrent subagents synthesized in one
request) replacing the sequential explore fan-out — one API call plans, searches, and
extracts in parallel. Gate: verify the beta is accessible with a plain API key; otherwise
the sequential pipeline stands and nothing else changes.
