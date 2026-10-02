"""AI 测试夹具。"""

from __future__ import annotations

import pytest

from boardgames.ai import AIEngineParams, engine_keys, get_engine
from boardgames.games.quoridor.rules import QuoridorGame


@pytest.fixture
def game() -> QuoridorGame:
    return QuoridorGame()


@pytest.fixture(params=engine_keys())
def engine(request):
    """参数化跑遍所有已注册引擎，保证统一契约。"""
    return get_engine(request.param)


@pytest.fixture
def fast_params():
    def _make(**changes) -> AIEngineParams:
        base = AIEngineParams(
            time_limit_ms=400,
            depth=3,
            wall_depth=2,
            iterations=200,
            max_branch=8,
            seed=12345,
        )
        return base.copy(**changes)

    return _make
