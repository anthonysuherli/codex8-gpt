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
