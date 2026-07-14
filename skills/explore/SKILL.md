---
name: codex8-explore
description: Research a project topic and persist the findings in the codex8 knowledge base. Use when existing coverage is sparse or missing.
---

# codex8 explore

1. Resolve target: project = repo folder name, kb = current git branch (fall back to
   "main"). The user can override both.
2. Warn the user that `codex8_explore` blocks for 1–3 minutes and requires `OPENAI_API_KEY`.
3. Call the `codex8_explore` MCP tool with `{project, kb, prompt}`.
4. After it completes, re-run `codex8_resume` to show the updated coverage and preamble.
