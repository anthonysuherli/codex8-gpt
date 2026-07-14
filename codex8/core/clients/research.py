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
