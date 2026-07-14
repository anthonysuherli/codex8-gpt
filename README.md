# codex8

Knowledge engine plugin for **Codex** — research/ingest the web into per-project knowledge
bases, then tap them from any Codex session as an always-on `<preamble>` with coverage
banding (`rich`/`sparse`/`gap`). **GPT-5.6 is the only agent, `OPENAI_API_KEY` the only
credential, SQLite the only store.**

A hard fork of the [delapan](https://delapan.ai) engine, ported to Codex for
**OpenAI Build Week 2026** (Developer Tools track).

> **Status: pre-build scaffold.** `SPEC.md` is the architecture, `docs/PLAN.md` the
> task-by-task build plan, `docs/CODEX-SESSION.md` the session playbook. The engine lands
> as the plan executes; the sections below are filled in by Task 12.

## Quick start (Task 12 finalizes this)

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env        # add OPENAI_API_KEY
./install.sh                # wires [mcp_servers.codex8] + skills into ~/.codex
```

## Judge quick-path (Task 12 finalizes this)

Pre-seeded demo KB at `data/demo.db` — recall works with no exploration run:

```bash
CODEX8_DB_PATH=data/demo.db codex   # then: use the codex8-search skill, project codex8-demo, kb build-week
```

## Built with Codex

Written at the end of the build (Task 12): where Codex accelerated the port, where key
decisions were made, with commit references.

## License

MIT — see [LICENSE](LICENSE).
