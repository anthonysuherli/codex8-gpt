---
name: codex8-search
description: Search the codex8 knowledge base for ranked project findings. Use for project-specific questions when a focused query is more useful than a resume card.
---

# codex8 search

1. Resolve target: project = repo folder name, kb = current git branch (fall back to
   "main"). The user can override both.
2. Call the `codex8_search` MCP tool with `{project, kb, query, limit?}`.
3. Answer from the ranked findings and cite each finding title that supports the answer.
4. If there are no relevant findings, say that the KB has a gap and offer `codex8-explore`.
