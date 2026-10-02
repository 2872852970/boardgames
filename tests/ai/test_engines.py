"""各引擎自身的特性。"""

from __future__ import annotations

import time

from boardgames.ai import AIEngineParams, SearchContext, get_engine
from boardgames.games.quoridor.move import PawnMove
from boardgames.games.quoridor.state import QuoridorState


def make_state(pawns, current=0) -> QuoridorState:
    return QuoridorState(
        size=9,
        pawns=pawns,
        walls_left=(10, 10),
        h_mask=0,
        v_mask=0,
        current=current,
        ply=0,
    )


# --------------------------------------------------------------------------- #
# Minimax
# --------------------------------------------------------------------------- #

def test_minimax_reports_depth_and_nodes(game, fast_params):
    engine = get_engine("minimax")
    stats = engine.search(
        game, game.initial_state(), 0, fast_params(depth=3), SearchContext(3000)
    ).stats
    assert stats.depth_reached >= 1
    assert stats.nodes > 0


def test_minimax_uses_transposition_table(game, fast_params):
    engine = get_engine("minimax")
    engine.search(
        game, game.initial_state(), 0, fast_params(depth=3, tt_enabled=True), SearchContext(3000)
    )
    assert engine.tt is not None
    assert engine.tt.stores > 0
    assert len(engine.tt) > 0


def test_minimax_without_tt_still_works(game, fast_params):
    engine = get_engine("minimax")
    result = engine.search(
        game, game.initial_state(), 0, fast_params(depth=2, tt_enabled=False), SearchContext(3000)
    )
    assert engine.tt is None
    assert result.move is not None


# --------------------------------------------------------------------------- #
# MCTS
# --------------------------------------------------------------------------- #

def test_mcts_reproducible_with_seed(game):
    engine = get_engine("mcts")
    params = AIEngineParams(iterations=150, max_branch=8, time_limit_ms=10_000, seed=2024)
    first = engine.search(game, game.initial_state(), 0, params, SearchContext(10_000))
    second = engine.search(game, game.initial_state(), 0, params, SearchContext(10_000))
    assert first.move == second.move


def test_mcts_reports_iterations_and_win_rate(game, fast_params):
    engine = get_engine("mcts")
    stats = engine.search(
        game, game.initial_state(), 0, fast_params(iterations=120, max_branch=8), SearchContext(10_000)
    ).stats
    assert stats.iterations > 0
    assert stats.win_rate is not None
    assert -1.0 <= stats.win_rate <= 1.0


def test_mcts_takes_immediate_win_instantly(game):
    engine = get_engine("mcts")
    winning = make_state(((4, 1), (4, 6)))
    result = engine.search(
        game,
        winning,
        0,
        AIEngineParams(iterations=10**6, time_limit_ms=30_000),
        SearchContext(30_000),
    )
    assert result.move == PawnMove((4, 1), (4, 0))
    assert result.stats.elapsed_ms < 200  # 直接命中必胜，不该真去搜索


# --------------------------------------------------------------------------- #
# 随机基线
# --------------------------------------------------------------------------- #

def test_random_engine_returns_legal_moves(game):
    engine = get_engine("random")
    state = game.initial_state()
    for _ in range(20):
        result = engine.search(game, state, 0, AIEngineParams(seed=1), SearchContext(100))
        assert result.move is not None
        assert game.is_legal(state, result.move)


# --------------------------------------------------------------------------- #
# 时限
# --------------------------------------------------------------------------- #

def test_no_engine_exceeds_time_limit(game):
    for key in ("minimax", "mcts"):
        engine = get_engine(key)
        params = AIEngineParams(time_limit_ms=200, depth=14, iterations=10**7, max_branch=12)
        t0 = time.perf_counter()
        engine.search(game, game.initial_state(), 0, params, SearchContext(200))
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 200 * 2.0 + 250, f"{key} 超时 {elapsed:.0f}ms"
