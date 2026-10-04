"""四个引擎在播棋上必须满足的统一契约。"""

from __future__ import annotations

import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext, engine_keys, get_engine
from boardgames.games.mancala.rules import MancalaGame
from boardgames.games.mancala.state import MancalaState


def make_state(
    pits: list[int],
    stores: tuple[int, int] = (0, 0),
    *,
    current: int = 0,
) -> MancalaState:
    return MancalaState(
        pits_per_side=6, pits=tuple(pits), stores=stores, current=current, ply=0,
    )


@pytest.fixture(params=engine_keys())
def engine(request):
    return get_engine(request.param)


@pytest.fixture
def game():
    return MancalaGame()


@pytest.fixture
def fast_params():
    def _make(**changes) -> AIEngineParams:
        base = AIEngineParams(
            time_limit_ms=300, depth=3, wall_depth=2, iterations=150, max_branch=8, seed=12345,
        )
        return base.copy(**changes)

    return _make


def test_returns_legal_move_from_initial_position(game, engine, fast_params):
    state = game.initial_state()
    result = engine.search(game, state, 0, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)
    assert result.stats.engine == engine.key


def test_returns_legal_move_midgame(game, engine, fast_params):
    state = make_state([3, 5, 0, 7, 2, 1, 4, 0, 6, 3, 8, 2], stores=(4, 3), current=0)
    result = engine.search(game, state, state.current, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    from dataclasses import replace

    state = replace(make_state([0] * 12, stores=(24, 24)), over=True)
    assert state.is_terminal()
    result = engine.search(game, state, 0, fast_params(), SearchContext(200))
    assert result.move is None


def test_time_limit_is_respected(game, engine):
    params = AIEngineParams(time_limit_ms=250, depth=12, iterations=10**7, max_branch=12)
    state = game.initial_state()
    t0 = time.perf_counter()
    engine.search(game, state, 0, params, SearchContext(250))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 250 * 2.0 + 250, f"超时: {elapsed_ms:.0f}ms"


def test_stats_are_populated(game, engine, fast_params):
    state = game.initial_state()
    stats = engine.search(game, state, 0, fast_params(), SearchContext(400)).stats
    assert stats.elapsed_ms > 0
    assert stats.engine_name
    assert isinstance(stats.summary(), str)


def test_random_engine_also_plays(game, engine, fast_params):
    if engine.key != "random":
        pytest.skip("只测随机引擎")
    state = game.initial_state()
    result = engine.search(game, state, 0, fast_params(), SearchContext(200))
    assert result.move is not None
    assert game.is_legal(state, result.move)
