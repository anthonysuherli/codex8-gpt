from __future__ import annotations

import pytest


@pytest.fixture
def fake_embedding() -> list[float]:
    return [0.1] * 1536


@pytest.fixture
def fake_embedding_other() -> list[float]:
    return [-0.1] * 1536
