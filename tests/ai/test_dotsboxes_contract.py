"""四个引擎在点格棋上必须满足的统一契约。"""

from __future__ import annotations

import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext, engine_keys, get_engine
from boardgames.games.dotsboxes.rules import DotsBoxesGame
from boardgames.games.dotsboxes.state import DotsBoxesState


def make_state(
    size: int = 3,
    h_edges: set[tuple[int, int]] | None = None,
    v_edges: set[tuple[int, int]] | None = None,
    *,
    current: int = 0,
) -> DotsBoxesState:
    n = size
    h = tuple(1 if (r, c) in (h_edges or set()) else 0 for r in range(n) for c in range(n - 1))
    v = tuple(1 if (r, c) in (v_edges or set()) else 0 for r in range(n - 1) for c in range(n))
    ply = sum(1 for x in h if x) + sum(1 for x in v if x)
    return DotsBoxesState(
        size=n, h_edges=h, v_edges=v, boxes=(0,) * ((n - 1) * (n - 1)),
        scores=(0, 0), current=current, ply=ply,
    )


@pytest.fixture(params=engine_keys())
def engine(request):
    return get_engine(request.param)


@pytest.fixture
def game():
    return DotsBoxesGame(size=3)


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
    state = make_state(3, h_edges={(0, 0), (1, 0)}, v_edges={(0, 0)}, current=0)
    result = engine.search(game, state, state.current, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    h = {(r, c) for r in range(3) for c in range(2)}
    v = {(r, c) for r in range(2) for c in range(3)}
    full = make_state(3, h_edges=h, v_edges=v)
    # 用 apply 走到真正终局
    from boardgames.games.dotsboxes.state import DotsBoxesState

    done = DotsBoxesState(
        size=3, h_edges=full.h_edges, v_edges=full.v_edges,
        boxes=(1,) * 4, scores=(4, 0), current=0, ply=12, winner_player=0,
    )
    assert done.is_terminal()
    result = engine.search(game, done, 0, fast_params(), SearchContext(200))
    assert result.move is None


def test_finds_immediate_box(game, engine, fast_params):
    """三条边已画好 → 会思考的引擎必须封口（随机引擎除外）。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    # (0,0) 格三条边已画，只差右边垂直边
    state = make_state(3, h_edges={(0, 0), (1, 0)}, v_edges={(0, 0)}, current=0)
    result = engine.search(game, state, 0, fast_params(), SearchContext(500))
    assert result.move is not None
    from boardgames.games.dotsboxes.move import EdgeMove

    assert isinstance(result.move, EdgeMove)
    # 封口边是 (1, 0, 1)（垂直边，第0行第1列）
    assert (result.move.orient, result.move.row, result.move.col) == (1, 0, 1)


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
