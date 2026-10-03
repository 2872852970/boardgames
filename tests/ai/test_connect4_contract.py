"""四个引擎在四子棋上必须满足的统一契约。

与 ``test_engine_contract.py``（墙棋）分开写而不是参数化两种游戏：
共用夹具会把测试数量翻倍且耦合两个棋类，分开更清晰、失败时也更容易定位。
"""

from __future__ import annotations

import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext, engine_keys, get_engine
from boardgames.games.connect4.rules import Connect4Game
from boardgames.games.connect4.state import Connect4State


def make_at(cols: int, rows: int, pieces: dict[tuple[int, int], int], *, fill: int = 0, current: int = 0):
    """按坐标造局面（其余格子留空）。这里自带一份，避免依赖 games 目录的 conftest。"""
    cells = [fill] * (cols * rows)
    for (c, r), value in pieces.items():
        cells[r * cols + c] = value
    heights = []
    for c in range(cols):
        height = 0
        for r in range(rows):
            if cells[r * cols + c] != 0:
                height = r + 1
        heights.append(height)
    return Connect4State(
        cols=cols, rows=rows, cells=tuple(cells), heights=tuple(heights),
        current=current, ply=sum(1 for v in cells if v), winner_player=None,
    )


@pytest.fixture(params=engine_keys())
def engine(request):
    return get_engine(request.param)


@pytest.fixture
def game():
    return Connect4Game()


@pytest.fixture
def fast_params():
    def _make(**changes) -> AIEngineParams:
        base = AIEngineParams(
            time_limit_ms=300,
            depth=3,
            wall_depth=2,
            iterations=150,
            max_branch=8,
            seed=12345,
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
    state = make_at(7, 6, {
        (3, 0): 1, (3, 1): 1, (2, 0): 2, (4, 0): 2, (2, 1): 2, (3, 2): 2,
    })
    result = engine.search(game, state, state.current, fast_params(), SearchContext(400))
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    state = make_at(6, 6, {(c, 0): 1 for c in range(4)})
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 4))
    assert won.is_terminal()
    result = engine.search(game, won, 0, fast_params(), SearchContext(200))
    assert result.move is None


def test_finds_immediate_win(game, engine, fast_params):
    """三连（下一手就能赢）→ 会思考的引擎都必须抓住（随机引擎除外）。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    state = make_at(7, 6, {(c, 0): 1 for c in (0, 1, 2)}, current=0)
    result = engine.search(game, state, 0, fast_params(), SearchContext(500))
    assert result.move is not None
    assert result.move.col == 3, f"{engine.key} 应当直接投第 4 列取胜"


def test_blocks_opponent_immediate_win(game, engine, fast_params):
    """对手三连，必须堵（不堵就输）。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    state = make_at(7, 6, {(c, 0): 2 for c in (0, 1, 2)}, current=0)
    result = engine.search(game, state, 0, fast_params(), SearchContext(500))
    assert result.move is not None
    assert result.move.col == 3, f"{engine.key} 应当堵住第 4 列"


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


def test_deep_search_finds_forced_win(game):
    """深度搜索在"三连 + 潜在双threat"局面应能找到取胜手。"""
    if engine_keys() and "minimax" not in engine_keys():
        pytest.skip("minimax 未注册")
    engine = get_engine("minimax")
    # 玩家1 在 col0,1,2 有三连（下一手赢），col3 空的
    state = make_at(7, 6, {(c, 0): 1 for c in (0, 1, 2)}, current=0)
    params = AIEngineParams(time_limit_ms=500, depth=4, max_branch=8, seed=1)
    result = engine.search(game, state, 0, params, SearchContext(600))
    assert result.move.col == 3
