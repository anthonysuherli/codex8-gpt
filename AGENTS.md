# AGENTS.md — codex8

You are building **codex8**: a hard fork of the delapan knowledge engine ported to a
Codex/GPT-5.6 plugin. Read `SPEC.md` first (architecture, constraints, scope cuts), then
execute `docs/PLAN.md` task-by-task, in order. Do not skip ahead; do not batch commits.

## Commands

```bash
uv venv && uv pip install -e ".[dev]"     # bootstrap (Python 3.12+)
.venv/bin/pytest                          # tests — must be green before every commit
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Hard rules

- **Single credential.** Only `OPENAI_API_KEY` (from `.env`, never committed). If you find
  yourself needing another key, stop — the design is wrong; re-read SPEC.md constraint 1.
- **`_upstream/delapan/` is read-only.** It is the frozen prior-work snapshot. Port by
  copying files out of it and renaming imports `delapan.*` → `codex8.*`. Never edit,
  delete, or import from `_upstream`.
- **No cross-repo imports.** No `from delapan…`, no `from br8n…`. codex8 stands alone.
- **TDD.** Each task in `docs/PLAN.md` carries its own tests — write the failing test
  first, then port/implement, then run to green, then commit.
- **Commit per task**, message format `feat: <task title>` / `test: …` / `chore: …`.
  Small commits are competition evidence — do not squash.
- **Tests must not call the network.** Mock OpenAI client calls; use `tmp_path` SQLite DBs
  and fake 1536-dim embeddings. Live smoke tests live in `scripts/` and are run manually.

## House style (match upstream exactly)

`from __future__ import annotations` first in every module; full type hints; terse module
docstrings that open with an ASCII flow diagram; ruff line-length 100. When porting a file,
preserve its structure and comments — change only imports, env prefixes (`DLP_` → `C8_`),
model IDs, and the seams named in the plan.

## Verification anchors

- Store contract: `codex8/store/sqlite.py` must satisfy every method the MCP server calls
  (`match_findings`, `insert_findings`, `create_exploration`, project/KB resolution).
- Embedding dim is **1536** end-to-end (`text-embedding-3-small` native = `vec0 float[1536]`).
- After Phase 2, the plugin must work in a real Codex session with **no** API key for
  resume/search on `data/demo.db`.
