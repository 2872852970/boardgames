"""四个引擎在大力士棋上必须满足的统一契约。

与 ``test_engine_contract.py``（墙棋）/ ``test_connect4_contract.py``（四子棋）分开写
而不是参数化三种游戏：共用夹具会把测试数量翻三倍且把三个棋类耦合到一起，
分开更清晰、失败时也更容易定位。

大力士棋在这里有两个**别处没有**的契约，都是踩过的坑：

* ``max_branch`` 是真的生效的（开局 44 步，不裁剪会炸）—— 墙棋/四子棋都不该用它，
  但这里必须验证它确实能砍，**且砍完仍然是合法着法**；
* ``include_walls`` / ``include_special`` 必须**被忽略**：那是给墙棋的墙位排序用的，
  当成"裁剪着法"会让深层节点只剩不到一个候选，棋力直接崩且查不出原因。
"""

from __future__ import annotations

import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext, engine_keys, get_engine
from boardgames.core.game import SearchOptions
from boardgames.games.abalone.geometry import CELL_COUNT, INDEX
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState

E, NE, NW, W, SW, SE = range(6)


def make_state(
    pieces: dict[tuple[int, int], int],
    *,
    out: tuple[int, int] = (0, 0),
    current: int = 0,
    ply: int = 0,
) -> AbaloneState:
    """按坐标造局面（其余 61 格留空）。这里自带一份，避免跨目录 import。"""
    cells = [0] * CELL_COUNT
    for pos, value in pieces.items():
        cells[INDEX[pos]] = value
    return AbaloneState(
        cells=tuple(cells), out=out, current=current, ply=ply, winner_player=None
    )


@pytest.fixture(params=engine_keys())
def engine(request):
    return get_engine(request.param)


@pytest.fixture
def game():
    return AbaloneGame()


@pytest.fixture
def fast_params():
    def _make(**changes) -> AIEngineParams:
        base = AIEngineParams(
            time_limit_ms=300,
            depth=3,
            wall_depth=2,
            iterations=150,
            max_branch=12,
            rollout_depth_cap=24,
            seed=12345,
        )
        return base.copy(**changes)

    return _make


def search(game, engine, state, params, budget=None):
    return engine.search(game, state, state.current, params, SearchContext(budget or 400))


# --------------------------------------------------------------------------- #
# 基本契约
# --------------------------------------------------------------------------- #

def test_returns_legal_move_from_initial_position(game, engine, fast_params):
    for setup in ("standard", "belgian_daisy", "german_daisy"):
        g = AbaloneGame(setup)
        result = search(g, engine, g.initial_state(), fast_params())
        assert result.move is not None, setup
        assert g.is_legal(g.initial_state(), result.move), setup


def test_returns_legal_move_midgame(game, engine, fast_params):
    state = make_state({(0, 0): 1, (1, 0): 1, (-1, 0): 2, (-2, 0): 2, (0, -2): 1})
    result = search(game, engine, state, fast_params())
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0))
    over = game.apply(state, next(m for m in game.legal_moves(state) if len(m.cells) == 2))
    assert over.is_terminal()
    assert search(game, engine, over, fast_params(), 200).move is None


def test_stats_are_populated(game, engine, fast_params):
    stats = search(game, engine, game.initial_state(), fast_params()).stats
    assert stats.elapsed_ms > 0
    assert stats.engine_name
    assert isinstance(stats.summary(), str)


def test_time_limit_is_respected(game, engine):
    params = AIEngineParams(
        time_limit_ms=250, depth=12, iterations=10**7, max_branch=16, rollout_depth_cap=30
    )
    t0 = time.perf_counter()
    search(game, engine, game.initial_state(), params, 250)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 250 * 2.0 + 250, f"超时: {elapsed_ms:.0f}ms"


def test_random_engine_also_plays(game, engine, fast_params):
    if engine.key != "random":
        pytest.skip("只测随机引擎")
    state = game.initial_state()
    move = search(game, engine, state, fast_params(), 200).move
    assert move is not None and game.is_legal(state, move)


# --------------------------------------------------------------------------- #
# 棋力：必须抓得住一步胜负
# --------------------------------------------------------------------------- #

def test_finds_the_winning_ejection(game, engine, fast_params):
    """把对手最后一枚推下盘就赢 —— 会思考的引擎都必须抓住。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    # P0 两枚压在边界上，前方一枚 P1 的子：向 E 推进即把它挤出盘外
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0))
    result = engine.search(game, state, 0, fast_params(), SearchContext(500))
    assert result.move is not None
    assert result.move.direction == E, f"{engine.key} 应当直接向 E 推出最后一枚"
    assert len(result.move.cells) == 2


def test_takes_a_free_ejection(game, engine, fast_params):
    """不付出任何代价就能把对手一枚挤下盘 —— 会思考的引擎都不该放过。

    背景子只是为了别让某一方清零（``is_terminal`` 的防御性条款会把那种手搭局面
    判成终局），它们离得很远，不参与这一手的取舍。
    """
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2, (-4, 4): 1, (0, -4): 2})
    result = engine.search(game, state, 0, fast_params(depth=3, iterations=400),
                           SearchContext(700))
    assert result.move is not None
    assert result.move.cells == ((2, 0), (3, 0)), f"{engine.key} 选了 {result.move.describe()}"
    assert result.move.direction == E


def test_does_not_walk_itself_off_the_board(game, engine, fast_params):
    """哪怕是随机引擎，出的也只能是合法着法 —— 合法性里已含"不许自杀出界"。

    （大力士棋里己方棋子被自己推下去是不存在的选项，这里用它当通用不变式。）
    """
    state = make_state({(4, 0): 1, (3, 0): 1, (-4, 0): 2})
    before = state.marble_count()
    move = search(game, engine, state, fast_params(), 300).move
    if move is None:
        pytest.skip("局面无着法")
    after = game.apply(state, move)
    assert after.marble_count()[0] >= before[0] - 0, "自己不可能掉子"


# --------------------------------------------------------------------------- #
# 搜索选项：只认 max_branch
# --------------------------------------------------------------------------- #

def _uncapped(**kwargs) -> SearchOptions:
    """不受任何裁剪的选项。

    **必须显式给 ``max_branch`` 一个大数**：``SearchOptions`` 的默认值是 16，
    而大力士棋开局有 44 步 —— 直接 ``SearchOptions(include_walls=False)``
    会顺带把着法砍到 16 条，测试就变成在验 max_branch 而不是验这个开关了。
    """
    return SearchOptions(max_branch=10_000, **kwargs)


def test_max_branch_truncates_but_stays_legal(game):
    """``max_branch`` 是大力士棋**唯一**真正用到的裁剪开关（这里是默认就生效的）。"""
    state = game.initial_state()
    assert len(game.legal_moves(state)) == 44
    for cap in (1, 3, 8):
        trimmed = game.legal_moves(state, SearchOptions(max_branch=cap))
        assert 0 < len(trimmed) <= cap
        for move in trimmed:
            assert game.is_legal(state, move)


def test_wall_flags_are_ignored(game):
    """``include_walls`` / ``include_special`` 是墙棋专用，一律不得影响着法数量。

    当成"裁剪"会让深层节点只剩不到一个候选，棋力直接崩且查不出原因 ——
    四子棋已经踩过同一口井。
    """
    state = game.initial_state()
    plain = len(game.legal_moves(state, _uncapped()))
    for options in (
        _uncapped(include_walls=False),
        _uncapped(include_special=False),
        _uncapped(include_walls=False, include_special=False),
    ):
        assert len(game.legal_moves(state, options)) == plain


def test_ordering_does_not_change_the_move_set(game):
    state = game.initial_state()
    plain = set(game.legal_moves(state, _uncapped()))
    for options in (_uncapped(order=False), _uncapped(order=True)):
        assert set(game.legal_moves(state, options)) == plain


def test_truncation_keeps_the_tactical_moves(game):
    """**截断必须隐含排序** —— MCTS 传的是 ``order=False``。

    生成顺序是"先单子、后 LINES 表"，照它截会把推挤类着法系统性砍光：
    实测连"白送一枚挤出"都进不了搜索树。
    """
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2, (-4, 4): 1, (0, -4): 2})
    capped = 4
    trimmed = game.legal_moves(state, SearchOptions(max_branch=capped, order=False))
    assert len(trimmed) == capped
    assert any(move.ejected is not None for move in trimmed), "挤出型着法被裁掉了"


def test_search_survives_a_tiny_branch_cap(game, engine, fast_params):
    """侧栏把「着法候选上限」拉到最小值也不能崩/返回非法着法。"""
    state = game.initial_state()
    move = search(game, engine, state, fast_params(max_branch=1), 300).move
    if move is not None:
        assert game.is_legal(state, move)


# --------------------------------------------------------------------------- #
# 终局分数
# --------------------------------------------------------------------------- #

def test_engine_reports_a_terminal_position_as_decided(game, engine, fast_params):
    """已经分出胜负的局面：所有引擎都不该再"想"出一手。"""
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0))
    over = game.apply(state, next(m for m in game.legal_moves(state) if len(m.cells) == 2))
    assert over.winner() == 0
    assert engine.search(game, over, 0, fast_params(), SearchContext(200)).move is None


def test_a_full_random_game_terminates(game):
    """随机互走必须在有限步数内收敛（推射型棋恶心的地方是可能打转）。"""
    import random

    rng = random.Random(3)
    state = game.initial_state()
    steps = 0
    while not state.is_terminal() and steps < 400:
        state = game.apply(state, game.rollout_move(state, rng))
        steps += 1
    assert state.is_terminal(), f"走了 {steps} 步还没结束"
    assert state.winner() in (0, 1)
    assert max(state.out) == 6
