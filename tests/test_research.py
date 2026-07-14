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
    exception here would abort the whole exploration instead of dropping one query.
    """
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
