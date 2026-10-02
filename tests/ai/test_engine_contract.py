"""所有引擎必须满足的统一契约。"""

from __future__ import annotations

import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext
from boardgames.games.quoridor.move import PawnMove, WallMove


def test_returns_legal_move_from_initial_position(game, engine, fast_params):
    state = game.initial_state()
    result = engine.search(game, state, 0, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)
    assert result.stats.engine == engine.key


def test_returns_legal_move_midgame(game, engine, fast_params):
    state = game.initial_state()
    script = [
        PawnMove((4, 8), (4, 7)),
        WallMove("h", 3, 3),
        PawnMove((4, 7), (4, 6)),
        WallMove("v", 5, 4),
        PawnMove((4, 6), (5, 6)),
    ]
    for move in script:
        state = game.apply(state, move)
    result = engine.search(game, state, state.current, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    from boardgames.games.quoridor.state import QuoridorState

    terminal = QuoridorState(
        size=9,
        pawns=((4, 0), (4, 5)),
        walls_left=(10, 10),
        h_mask=0,
        v_mask=0,
        current=0,
        ply=0,
    )
    assert terminal.is_terminal()
    result = engine.search(game, terminal, 0, fast_params(), SearchContext(200))
    assert result.move is None


def test_finds_immediate_win(game, engine, fast_params):
    """一步到目标行 → 会思考的引擎都必须抓住（随机引擎除外）。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    from boardgames.games.quoridor.state import QuoridorState

    state = QuoridorState(
        size=9,
        pawns=((4, 1), (4, 7)),
        walls_left=(10, 10),
        h_mask=0,
        v_mask=0,
        current=0,
        ply=0,
    )
    result = engine.search(game, state, 0, fast_params(), SearchContext(400))
    assert result.move == PawnMove((4, 1), (4, 0))


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
