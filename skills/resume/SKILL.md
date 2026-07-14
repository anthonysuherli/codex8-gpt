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
