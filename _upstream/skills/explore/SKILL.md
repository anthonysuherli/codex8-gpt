---
name: delapan-explore
description: Run the gap-fill exploration pipeline (plan → search → crawl → extract → merge) when KB coverage is sparse or gap. Blocks ~1–3 minutes. Requires LLM and Tavily keys in backend/.env.
---

# Delapan Explore

Fill knowledge gaps from the web and merge new findings into the KB.

## Target resolution

```bash
git rev-parse --show-toplevel | xargs basename   # → project
git branch --show-current                         # → kb
```

## Workflow

1. Confirm explore is appropriate — coverage `gap`/`sparse`, or user explicitly asked to research/fill gaps.
2. Call **`delapan_explore`** with `project`, `kb`, and an optional focus prompt (user's topic).
3. Wait for completion (synchronous; may take 1–3 minutes).
4. Re-run **`delapan_resume`** to refresh preamble/coverage, then answer from updated findings.

## Prerequisites

- `ANTHROPIC_API_KEY`, `AI_GATEWAY_API_KEY`, or `OPENAI_API_KEY` in `backend/.env`
- `TAVILY_API_KEY` for web search

If keys are missing, tell the user which env vars to set — do not silently skip.
