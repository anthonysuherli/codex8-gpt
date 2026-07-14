from __future__ import annotations

from unittest.mock import AsyncMock

import codex8.core.exploration.engine as engine_mod
import codex8.core.exploration.evaluator as evaluator_mod
import codex8.core.exploration.extractor as extractor_mod
import codex8.core.exploration.planner as planner_mod
from codex8.core.exploration.models import (
    ExplorationPlan,
    FindingBatch,
    RawFinding,
    SearchQuery,
)


async def test_engine_uses_research_not_tavily():
    assert not hasattr(engine_mod, "tavily")
    assert hasattr(engine_mod, "research")


async def test_run_exploration_smoke(monkeypatch):
    from codex8.core.config import get_config
    from codex8.core.exploration import run_exploration

    monkeypatch.setattr(
        engine_mod.research,
        "search",
        AsyncMock(
            return_value=[{"url": "https://x.example/a", "title": "A", "content": "snippet"}]
        ),
    )
    monkeypatch.setattr(
        engine_mod.research,
        "extract",
        AsyncMock(return_value={"https://x.example/a": "Full page text about the topic."}),
    )
    monkeypatch.setattr(
        planner_mod,
        "structured_completion",
        AsyncMock(
            return_value=ExplorationPlan(
                search_queries=[SearchQuery(query="q1")],
                extraction_prompt="Extract concrete facts.",
                expected_categories=["c"],
                finding_title_hint="{fact}",
            )
        ),
    )
    monkeypatch.setattr(
        extractor_mod,
        "structured_completion",
        AsyncMock(
            return_value=FindingBatch(
                findings=[RawFinding(title="F1", content={"fact": "x"}, category="c")]
            )
        ),
    )
    monkeypatch.setattr(
        evaluator_mod,
        "structured_completion",
        AsyncMock(
            return_value=evaluator_mod._EvaluationBatch(
                verdicts=[evaluator_mod._FindingVerdict(index=0, quality=0.9, keep=True)]
            )
        ),
    )

    findings = await run_exploration(
        "topic",
        exploration_id="e1",
        project_id="p1",
        kb_id="k1",
        cfg=get_config().exploration,
    )
    assert findings
    f = findings[0]
    assert f.title == "F1"
    assert f.provenance == [{"url": "https://x.example/a", "query": "q1"}]
    assert abs(f.confidence - 0.36) < 1e-9
