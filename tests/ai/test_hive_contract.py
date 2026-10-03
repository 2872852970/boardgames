"""四个引擎在昆虫棋上必须满足的统一契约。

与 ``test_engine_contract.py``（墙棋）分开写：昆虫棋有两个别处没有的契约，
都是它自己踩出来的坑。

1. **无处可走时必须真的交出一个** :class:`PassMove` **，而不是 ``None``。**
   昆虫棋会自然出现"既无处放子又无棋可动"的局面（例如己方唯一一枚棋被对方
   甲虫压住）。空着法表会让 MCTS 的 rollout 循环一路索取到抛 ``RuntimeError``，
   而异常被 AI 线程吞掉，表现就是"AI 突然不下棋"。
2. **随机整局必须收敛。** 昆虫棋没有"步数上限就会自然分胜负"这回事 ——
   纯随机 rollout 会一路挪子到 400 手上限判和，拿不到任何价值信号，
   所以 ``rollout_move`` 是带噪声的贪心。这里验证它确实能走出终局。
"""

from __future__ import annotations

import random
import time

import pytest

from boardgames.ai import AIEngineParams, SearchContext, engine_keys, get_engine
from boardgames.core.game import SearchOptions
from boardgames.games.hive.geometry import Pos, neighbors
from boardgames.games.hive.move import MoveMove, PassMove
from boardgames.games.hive.pieces import Piece
from boardgames.games.hive.rules import HiveGame
from boardgames.games.hive.state import MAX_PLY, HiveState, pack

P = Piece


def make_state(
    pieces: dict[Pos, list[Piece]],
    *,
    current: int = 0,
    expansion: bool = False,
    winner_player: int | None = None,
    drawn: bool = False,
    ply: int = 0,
) -> HiveState:
    """按坐标造局面。这里自带一份，避免跨目录 import。"""
    mapping = {pos: tuple(stack) for pos, stack in pieces.items()}
    return HiveState(
        stacks=pack(mapping),
        played=(0, 0),
        current=current,
        ply=ply,
        expansion=expansion,
        winner_player=winner_player,
        drawn=drawn,
    )


def _almost_surrounded() -> dict:
    """蜂后 (0,0) 只差 (0,1) 一面；补刀的棋停在 **(1,1)** 上。

    (1,1) 不贴着蜂后 —— 只有从这种格子挪进 (0,1) 才会真的让包围数 +1。
    补刀的用**蜂后**，这样双方都有蜂后（没蜂后就不能移动任何棋子）。
    """
    board: dict[Pos, list[Piece]] = {(0, 0): [P(0, "queen")], (1, 1): [P(1, "queen")]}
    for n in neighbors((0, 0)):
        if n != (0, 1):
            board[n] = [P(1, "ant")]
    return board


#: 无子可走：己方唯一的棋被对方甲虫压住，既没有贴己方的落点也没有可动的棋
STUCK = {(0, 0): [P(0, "queen"), P(1, "beetle")], (1, 0): [P(1, "ant")]}

#: 中局：一条四格长的蜂巢，主角在 (0,0)
MIDGAME = {
    (0, 0): [P(0, "ant")],
    (1, 0): [P(1, "ant")],
    (2, 0): [P(1, "ant")],
    (3, 0): [P(0, "queen")],
}


@pytest.fixture(params=engine_keys())
def engine(request):
    return get_engine(request.param)


@pytest.fixture
def game():
    return HiveGame()


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
    state = game.initial_state()
    result = search(game, engine, state, fast_params())
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_returns_legal_move_midgame(game, engine, fast_params):
    state = make_state(MIDGAME, current=0)
    result = search(game, engine, state, fast_params())
    assert result.move is not None
    assert game.is_legal(state, result.move)


def test_terminal_state_returns_none(game, engine, fast_params):
    state = make_state({(0, 0): [P(0, "queen")]}, winner_player=0)
    assert state.is_terminal()
    assert search(game, engine, state, fast_params(), 200).move is None


def test_drawn_state_returns_none(game, engine, fast_params):
    """和棋也是终局 —— 引擎不该在已经判和的局面里继续"想"。"""
    state = make_state({(0, 0): [P(0, "queen")]}, drawn=True)
    assert search(game, engine, state, fast_params(), 200).move is None


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


# --------------------------------------------------------------------------- #
# 只能停一手的局面：四个引擎都必须交出 PassMove
# --------------------------------------------------------------------------- #


def test_every_engine_passes_instead_of_freezing(game, engine, fast_params):
    """这是昆虫棋**独有**的契约：无子可走时返回 ``None`` 就等于 AI 罢工。"""
    state = make_state(STUCK, current=0)
    assert game.legal_moves(state) == [PassMove(0)]
    result = search(game, engine, state, fast_params(), 300)
    assert result.move is not None, f"{engine.key} 在无子可走的局面返回了 None"
    assert isinstance(result.move, PassMove), f"{engine.key} 返回了 {result.move!r}"
    assert game.is_legal(state, result.move)


def test_a_pass_is_applied_without_crashing(game, engine, fast_params):
    state = make_state(STUCK, current=0)
    after = game.apply(state, search(game, engine, state, fast_params(), 300).move)
    assert after.current_player == 1
    assert after.passes == 1


# --------------------------------------------------------------------------- #
# 棋力：必须抓得住一步胜负
# --------------------------------------------------------------------------- #


def test_finds_the_mating_surround(game, engine, fast_params):
    """把敌后六面围满就赢 —— 会思考的引擎都必须抓住。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    state = make_state(_almost_surrounded(), current=1)
    result = engine.search(game, state, 1, fast_params(), SearchContext(500))
    assert result.move is not None
    assert game.apply(state, result.move).winner() == 1, (
        f"{engine.key} 选了 {result.move.describe()}"
    )


def test_the_mating_move_survives_a_tiny_branch_cap(game, engine, fast_params):
    """侧栏把「着法候选上限」拉到最小值时，也不能把制胜手裁掉。"""
    if engine.key == "random":
        pytest.skip("随机引擎不做搜索，不适用")
    state = make_state(_almost_surrounded(), current=1)
    result = engine.search(game, state, 1, fast_params(max_branch=1), SearchContext(300))
    assert result.move is not None
    assert game.apply(state, result.move).winner() == 1


def test_search_survives_a_tiny_branch_cap(game, engine, fast_params):
    state = make_state(MIDGAME, current=0)
    move = search(game, engine, state, fast_params(max_branch=1), 300).move
    if move is not None:
        assert game.is_legal(state, move)


# --------------------------------------------------------------------------- #
# 搜索选项：只认 max_branch
# --------------------------------------------------------------------------- #


def _uncapped(**kwargs) -> SearchOptions:
    """不受任何裁剪的选项。

    ``SearchOptions`` 的 ``max_branch`` 默认是 16，而昆虫棋中局有 70+ 着法 ——
    不显式放大就会顺带把着法砍到 16 条，测试就变成在验 max_branch 而不是
    验别的开关了。
    """
    return SearchOptions(max_branch=10_000, **kwargs)


def test_max_branch_truncates_but_stays_legal(game):
    state = make_state(MIDGAME, current=0)
    for cap in (1, 3, 8):
        trimmed = game.legal_moves(state, SearchOptions(max_branch=cap))
        assert 0 < len(trimmed) <= cap
        for move in trimmed:
            assert game.is_legal(state, move)


def test_wall_flags_are_ignored(game):
    """``include_walls`` / ``include_special`` 是墙棋专用，一律不得影响着法数量。"""
    state = make_state(MIDGAME, current=0)
    plain = len(game.legal_moves(state, _uncapped()))
    for options in (
        _uncapped(include_walls=False),
        _uncapped(include_special=False),
        _uncapped(include_walls=False, include_special=False),
    ):
        assert len(game.legal_moves(state, options)) == plain


def test_ordering_does_not_change_the_move_set(game):
    state = make_state(MIDGAME, current=0)
    plain = set(game.legal_moves(state, _uncapped()))
    for options in (_uncapped(order=False), _uncapped(order=True)):
        assert set(game.legal_moves(state, options)) == plain


def test_truncation_keeps_the_tactical_moves(game):
    """**截断必须隐含排序** —— MCTS 传的是 ``order=False``。

    生成顺序是"先放置、后移动"，照它截会把移动整类砍光，而"围死敌后"
    恰恰只能靠移动完成。
    """
    state = make_state(_almost_surrounded(), current=1)
    trimmed = game.legal_moves(state, SearchOptions(max_branch=4, order=False))
    assert len(trimmed) == 4
    assert any(
        isinstance(m, MoveMove) and m.dest == (0, 1) for m in trimmed
    ), "制胜的那一手被裁掉了"


# --------------------------------------------------------------------------- #
# 收敛性
# --------------------------------------------------------------------------- #


def test_a_full_random_game_terminates(game):
    """随机互走必须在有限步数内收敛。

    纯随机会一路挪子撞上 ``MAX_PLY`` 才判和（400 手），拿不到任何价值信号；
    ``rollout_move`` 因此做成带噪声的贪心。这里只要求**必然收敛**。
    """
    rng = random.Random(3)
    state = game.initial_state()
    steps = 0
    limit = MAX_PLY + 50
    while not state.is_terminal() and steps < limit:
        state = game.apply(state, game.rollout_move(state, rng))
        steps += 1
    assert state.is_terminal(), f"走了 {steps} 步还没结束"


def test_a_random_game_with_the_expansion_terminates():
    game = HiveGame(expansion=True)
    rng = random.Random(11)
    state = game.initial_state()
    steps = 0
    while not state.is_terminal() and steps < MAX_PLY + 50:
        state = game.apply(state, game.rollout_move(state, rng))
        steps += 1
    assert state.is_terminal(), f"走了 {steps} 步还没结束"


def test_rollout_never_returns_an_illegal_move(game):
    rng = random.Random(5)
    state = game.initial_state()
    for _ in range(120):
        if state.is_terminal():
            break
        move = game.rollout_move(state, rng)
        assert game.is_legal(state, move)
        state = game.apply(state, move)
