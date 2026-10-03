"""着法生成与推挤（sumito）规则。

``test_opening_move_counts`` 里那三个数字（44 / 52 / 80）是最值钱的一条回归：
它同时锁住"单子只生成一次"（否则会虚高）和"inline 反向没有忘记 reverse"
（否则两侧不对称、数字对不上）。
"""

from __future__ import annotations

import pytest
from aba_helpers import make_state

from boardgames.core.game import SearchOptions
from boardgames.games.abalone.geometry import CELLS, DIRECTIONS, INDEX, Pos
from boardgames.games.abalone.move import AbaloneMove
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState

E, NE, NW, W, SW, SE = range(6)


def mirror(state: AbaloneState) -> AbaloneState:
    """左右镜像：``(q, r) -> (-q - r, r)``，同时把双方颜色对调、行动方对调。"""
    cells = [0] * len(CELLS)
    for (q, r), value in zip(CELLS, state.cells, strict=True):
        if value:
            cells[INDEX[(-q - r, r)]] = 3 - value
    return AbaloneState(
        cells=tuple(cells),
        out=(state.out[1], state.out[0]),
        current=1 - state.current,
        ply=state.ply,
        winner_player=None,
    )


# --------------------------------------------------------------------------- #
# 开局着法数（锚定值）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("setup", "expected"),
    [("standard", 44), ("belgian_daisy", 52), ("german_daisy", 80)],
)
def test_opening_move_counts(game, setup, expected):
    moves = game.legal_moves(AbaloneGame(setup).initial_state())
    assert len(moves) == expected


def test_no_duplicate_moves(game):
    state = AbaloneGame("german_daisy").initial_state()
    moves = game.legal_moves(state)
    assert len(set(moves)) == len(moves), "着法表里有重复 —— 单子很可能被生成了多次"


def test_is_legal_accepts_every_generated_move(game, standard):
    for move in game.legal_moves(standard):
        assert game.is_legal(standard, move), f"{move.describe()} 被判非法"


def test_legal_moves_is_empty_on_terminal(game):
    state = make_state({(0, 0): 1}, out=(6, 0), current=1)
    assert state.is_terminal()
    assert game.legal_moves(state) == []


def test_all_opening_moves_are_mirror_symmetric(game):
    """镜像局面下着法数必须相同（专防 inline 反向忘记 reverse）。"""
    for setup in ("standard", "belgian_daisy", "german_daisy"):
        state = AbaloneGame(setup).initial_state()
        assert len(game.legal_moves(state)) == len(game.legal_moves(mirror(state)))


def test_midgame_move_count_is_mirror_symmetric(game):
    state = make_state(
        {
            (-2, 0): 1, (-1, 0): 1, (0, 0): 1, (1, 0): 2, (1, 1): 2,
            (-3, 2): 2, (0, 4): 1, (2, -2): 2, (-3, -1): 1,
        },
        current=0,
    )
    assert len(game.legal_moves(state)) == len(game.legal_moves(mirror(state)))


# --------------------------------------------------------------------------- #
# 单子
# --------------------------------------------------------------------------- #


def test_lone_marble_can_reach_all_six_neighbors(game):
    state = make_state({(0, 0): 1}, current=0)
    moves = game.legal_moves(state)
    assert len(moves) == 6
    assert all(len(m.cells) == 1 for m in moves)
    assert {m.direction for m in moves} == set(range(6))


def test_single_marble_cannot_push(game):
    """单子推不动 —— 2 推 1 才成立。"""
    state = make_state({(0, 0): 1, (1, 0): 2}, current=0)
    moves = game.legal_moves(state)
    single = [m for m in moves if m.cells == ((0, 0),)]
    assert len(single) == 5, "唯一走不了的方向应当正是被对手占住的那个"
    assert E not in {m.direction for m in single}
    assert all(not m.pushed and m.ejected is None for m in single)


def _dest(move: AbaloneMove) -> Pos:
    dq, dr = DIRECTIONS[move.direction]
    head = move.cells[-1]
    return (head[0] + dq, head[1] + dr)


# --------------------------------------------------------------------------- #
# 推挤：以多推少
# --------------------------------------------------------------------------- #


def _has(moves, group, direction) -> bool:
    return any(m.cells == tuple(sorted(group)) and m.direction == direction for m in moves)


@pytest.mark.parametrize(
    ("mine", "theirs", "legal"),
    [
        (2, 1, True),
        (3, 1, True),
        (3, 2, True),
        (1, 1, False),
        (2, 2, False),
        (3, 3, False),
    ],
)
def test_sumito_table(game, mine, theirs, legal):
    """己方 ``mine`` 枚推对手 ``theirs`` 枚。"""
    pieces = {(-3 + i, 0): 1 for i in range(mine)}
    pieces.update({(-3 + mine + i, 0): 2 for i in range(theirs)})
    # 再往后一格留空（保证不是"被别的子堵住"）
    state = make_state(pieces, current=0)
    moves = game.legal_moves(state)
    assert _has(moves, [(-3 + i, 0) for i in range(mine)], E) is legal


def test_cannot_push_when_backed_by_own_marble(game):
    """对手串后面是自己的子 -> 两侧夹住，推不动。"""
    state = make_state({(0, 0): 1, (1, 0): 1, (2, 0): 1, (3, 0): 2, (4, 0): 1}, current=0)
    assert not _has(game.legal_moves(state), [(0, 0), (1, 0), (2, 0)], E)


def test_cannot_push_a_block_of_three_or_more(game):
    """己方最多 3 枚，所以对手串到 3 枚就已经推不动了。"""
    own = [(-4, 0), (-3, 0), (-2, 0)]
    front = {p: 1 for p in own}

    three = make_state(front | {p: 2 for p in [(-1, 0), (0, 0), (1, 0)]}, current=0)
    assert not _has(game.legal_moves(three), own, E), "3 推 3 是对峙"

    four = make_state(
        front | {p: 2 for p in [(-1, 0), (0, 0), (1, 0), (2, 0)]}, current=0
    )
    assert not _has(game.legal_moves(four), own, E), "对手串比 3 还长"

    # 对照组：只有 2 枚挡着、后面空着 -> 3 推 2 成立
    two = make_state(front | {p: 2 for p in [(-1, 0), (0, 0)]}, current=0)
    assert _has(game.legal_moves(two), own, E)


def test_ejection_off_the_edge(game):
    """顶在盘边的对手子被 2 推 1 挤出去。"""
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, current=0)
    moves = game.legal_moves(state)
    ejecting = [m for m in moves if m.ejected is not None]
    assert len(ejecting) == 1
    assert ejecting[0].ejected == (4, 0)
    assert ejecting[0].pushed == ()
    assert ejecting[0].cells == ((2, 0), (3, 0))


def test_broadside_cannot_push(game):
    """横移时目标格被占（哪怕是对手）就不合法。"""
    state = make_state({(0, 0): 1, (1, 0): 1, (1, 1): 2}, current=0)
    assert not _has(game.legal_moves(state), [(0, 0), (1, 0)], SE)


def test_broadside_needs_all_targets_empty(game):
    state = make_state({(0, 0): 1, (1, 0): 1, (0, 1): 1}, current=0)
    # SE 的两个目标格是 (0,1) 与 (1,1)：(0,1) 有自己的子 -> 不合法
    assert not _has(game.legal_moves(state), [(0, 0), (1, 0)], SE)
    # SW 的目标格是 (-1,1) 与 (0,1)，(0,1) 有子 -> 同样不合法
    assert not _has(game.legal_moves(state), [(0, 0), (1, 0)], SW)


def test_inline_backwards_is_the_same_as_pushing_the_other_way(game):
    """3 子朝 W 前进 = 同一组朝 E 推的镜像；两侧都要能生成。"""
    state = make_state({(0, 0): 1, (1, 0): 1, (2, 0): 1, (3, 0): 2, (4, 0): 0}, current=0)
    moves = game.legal_moves(state)
    assert _has(moves, [(0, 0), (1, 0), (2, 0)], E)   # 往东推
    assert _has(moves, [(0, 0), (1, 0), (2, 0)], W)   # 往西撤（目标格为空）


# --------------------------------------------------------------------------- #
# 着法身份 / 搜索裁剪
# --------------------------------------------------------------------------- #


def test_move_equality_ignores_pushed_and_ejected():
    base = dict(player=0, cells=((0, 0), (1, 0)), direction=E)
    a = AbaloneMove(**base)
    b = AbaloneMove(**base, pushed=((2, 0),), ejected=(3, 0))
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1, "pushed/ejected 参与了哈希 —— MCTS 子节点会重复"


def test_is_legal_recomputes_instead_of_comparing_cached_fields(standard, game):
    """手搭的着法（没带 pushed/ejected）也必须被判为合法。

    ``apply`` / ``is_legal`` 一律**重算**规划，不去比对 ``legal_moves`` 的缓存列表 ——
    否则 UI 那边手搭的着法会因为缺字段被判非法。
    """
    for move in game.legal_moves(standard):
        plain = AbaloneMove(move.player, move.cells, move.direction)
        assert game.is_legal(standard, plain)
        assert game.apply(standard, plain) == game.apply(standard, move)


def test_illegal_move_shapes_are_rejected(standard, game):
    me = standard.current + 1
    own = [p for p, v in zip(CELLS, standard.cells, strict=True) if v == me]
    # 空的组
    assert not game.is_legal(standard, AbaloneMove(0, (), 0))
    # 组里混进了对手的子
    assert not game.is_legal(standard, AbaloneMove(0, (own[0], (0, 0)), 0))
    # 4 子组
    assert not game.is_legal(standard, AbaloneMove(0, own[:4], 0))
    # 方向越界
    assert not game.is_legal(standard, AbaloneMove(0, (own[0],), 6))
    # 行动方不是自己
    assert not game.is_legal(standard, AbaloneMove(1, (own[0],), 0))
    # 不是 AbaloneMove
    assert not game.is_legal(standard, "not a move")


def test_max_branch_caps_but_include_walls_does_not(game, standard):
    """``max_branch`` 裁剪着法；``include_walls`` 是墙棋语义，必须被忽略。"""
    off = SearchOptions(max_branch=0, order=False, include_walls=False)
    on = SearchOptions(max_branch=0, order=False, include_walls=True)
    assert game.legal_moves(standard, off) == game.legal_moves(standard, on)

    capped = game.legal_moves(standard, SearchOptions(max_branch=5))
    assert len(capped) == 5


def test_ordering_prefers_ejections(game):
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2, (-2, -2): 1}, current=0)
    moves = game.legal_moves(state, SearchOptions(order=True))
    assert moves[0].ejected is not None
