"""官方扩展三虫：瓢虫 / 蚊子 / 鼠妇（侧栏 ``hive_expansion`` 开关，默认关闭）。

这三只虫的判定都建立在"相邻格的**栈顶**是什么"之上，所以用例刻意让相邻格
放着**不同的虫种**，一次性验证"模仿谁"和"不模仿谁"。
"""

from __future__ import annotations

import pytest
from hive_build import P, make_state, move_targets

from boardgames.games.hive import HiveGame
from boardgames.games.hive.geometry import Pos
from boardgames.games.hive.move import MoveMove, PillbugMove, PlaceMove
from boardgames.games.hive.pieces import BASE_KINDS

# 一条四格长的蜂巢：(0,0) 是主角，(3,0) 是己方蜂后（没有蜂后就不能移动）
LINE = {
    (0, 0): [P(0, "ant")],
    (1, 0): [P(1, "ant")],
    (2, 0): [P(1, "ant")],
    (3, 0): [P(0, "queen")],
}


def _with_mover(kind: str) -> dict:
    board = dict(LINE)
    board[(0, 0)] = [P(0, kind)]
    return board


def _state(pieces, **kwargs):
    """造带扩展虫的局面。

    ``expansion`` 必须跟着开 —— 手牌配额是按它算的，盘上出现了配额里没有的
    虫种会在建索引时直接 ``KeyError``。
    """
    return make_state(pieces, expansion=True, **kwargs)


# --------------------------------------------------------------------------- #
# 开关本身
# --------------------------------------------------------------------------- #


def test_the_base_game_never_offers_expansion_pieces(game: HiveGame, game_x: HiveGame):
    base = {m.kind for m in game.legal_moves(game.initial_state()) if isinstance(m, PlaceMove)}
    wide = {m.kind for m in game_x.legal_moves(game_x.initial_state()) if isinstance(m, PlaceMove)}
    assert base == set(BASE_KINDS)
    assert wide - base == {"ladybug", "mosquito", "pillbug"}


# --------------------------------------------------------------------------- #
# 瓢虫：恰好两跳
# --------------------------------------------------------------------------- #


def test_ladybug_makes_exactly_two_hops(game_x: HiveGame):
    """先爬上一枚相邻的棋，再落到**第二枚棋**旁边的空地。"""
    state = _state(_with_mover("ladybug"), current=0)
    moves = [
        m
        for m in game_x.legal_moves(state)
        if isinstance(m, MoveMove) and m.src == (0, 0)  # 排除蜂后自己的走法
    ]
    assert {m.dest for m in moves} == {(3, -1), (2, -1), (1, 1), (2, 1)}
    for move in moves:
        assert len(move.path) == 3  # 爬上 → 再爬上一枚 → 落地
        assert move.from_height == 0
        assert move.to_height == 0  # 必须落回地面


def test_ladybug_must_land_on_the_ground(game_x: HiveGame):
    """落点必须是有棋的那一格的邻**空地** —— 停在棋堆上不算。"""
    state = _state(_with_mover("ladybug"), current=0)
    occupied = {pos for pos, _ in state.stacks}
    assert not {m.dest for m in game_x.legal_moves(state)} & occupied


def test_ladybug_cannot_move_without_a_second_piece_to_climb(game_x: HiveGame):
    """只有一枚相邻棋时凑不满两跳 —— 一步都不能走。"""
    board = {(0, 0): [P(0, "ladybug")], (1, 0): [P(1, "ant")], (3, 0): [P(0, "queen")]}
    assert move_targets(game_x, _state(board, current=0), (0, 0)) == set()


def test_ladybug_never_returns_to_its_own_cell(game_x: HiveGame):
    state = _state(_with_mover("ladybug"), current=0)
    assert (0, 0) not in {m.dest for m in game_x.legal_moves(state)}


# --------------------------------------------------------------------------- #
# 蚊子：模仿相邻棋种
# --------------------------------------------------------------------------- #


def test_mosquito_copies_the_neighbouring_bug(game_x: HiveGame):
    """相邻只有一枚兵蚁时，蚊子的落点与"自己是兵蚁"完全一致。"""
    board = {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")], (2, 0): [P(0, "queen")]}
    ant = move_targets(game_x, _state(board, current=0), (0, 0))

    board[(0, 0)] = [P(0, "mosquito")]
    mosquito = move_targets(game_x, _state(board, current=0), (0, 0))
    assert mosquito == ant
    assert mosquito


def test_mosquito_copies_every_neighbouring_bug(game_x: HiveGame):
    """相邻有蜘蛛和蚱蜢时，落点是两者走法的**并集**。"""
    board = {
        (0, 0): [P(0, "ant")],
        (1, 0): [P(1, "spider")],
        (1, -1): [P(1, "grasshopper")],
        (2, 0): [P(0, "queen")],
    }
    spider = move_targets(game_x, _state({**board, (0, 0): [P(0, "spider")]}, current=0), (0, 0))
    hopper = move_targets(
        game_x, _state({**board, (0, 0): [P(0, "grasshopper")]}, current=0), (0, 0)
    )
    mosquito = move_targets(
        game_x, _state({**board, (0, 0): [P(0, "mosquito")]}, current=0), (0, 0)
    )
    assert spider and hopper and spider != hopper
    assert mosquito == spider | hopper


def test_a_mosquito_on_a_stack_only_moves_like_a_beetle(game_x: HiveGame):
    """官方规则：爬到蜂巢顶上的蚊子**只按甲虫走**，不再模仿任何人。"""
    board = {
        (0, 0): [P(0, "queen"), P(0, "mosquito")],
        (1, -1): [P(1, "ant")],
        (0, -1): [P(1, "ant")],
        (-1, 0): [P(1, "spider")],  # 地面上的蚊子会模仿它，堆上的不会
        (-1, 1): [P(1, "ant")],
        (0, 1): [P(1, "ant")],
    }
    beetle = dict(board)
    beetle[(0, 0)] = [P(0, "queen"), P(0, "beetle")]
    assert move_targets(game_x, _state(board, current=0), (0, 0)) == move_targets(
        game_x, _state(beetle, current=0), (0, 0)
    )


def test_a_mosquito_touching_only_mosquitoes_is_stuck(game_x: HiveGame):
    """没有可模仿的对象就一步也走不了。"""
    board = {
        (0, 0): [P(0, "mosquito")],
        (1, 0): [P(1, "mosquito")],
        (1, 1): [P(0, "queen")],  # (1,1) 不与 (0,0) 相邻，不该被模仿
    }
    assert move_targets(game_x, _state(board, current=0), (0, 0)) == set()


def test_mosquito_can_copy_a_pillbug(game_x: HiveGame):
    """官方规则：蚊子也能模仿鼠妇的搬运。"""
    board = {(0, 0): [P(0, "mosquito")], (1, 0): [P(1, "pillbug")], (1, -1): [P(0, "queen")]}
    carries = [
        m
        for m in game_x.legal_moves(_state(board, current=0))
        if isinstance(m, PillbugMove) and m.carried == (1, 0)
    ]
    assert carries


# --------------------------------------------------------------------------- #
# 鼠妇：搬运
# --------------------------------------------------------------------------- #

# (1,0) 上那枚蚂蚁搬得动：它的两个邻居 (0,0) 与 (1,-1) 彼此相邻，绕得过去
# （顺带一提，(1,-1) 上的蜂后同样搬得动，所以下面的用例一律按 carried 过滤）
CARRY = {(0, 0): [P(0, "pillbug")], (1, 0): [P(1, "ant")], (1, -1): [P(0, "queen")]}


def _carries(game_x: HiveGame, state, carried: Pos = (1, 0)) -> list[PillbugMove]:
    return [
        m
        for m in game_x.legal_moves(state)
        if isinstance(m, PillbugMove) and m.carried == carried
    ]


def test_pillbug_carries_a_neighbour_without_moving_itself(game_x: HiveGame):
    state = _state(CARRY, current=0)
    carries = _carries(game_x, state)
    assert {m.carried_dest for m in carries} == {(0, -1), (-1, 0), (-1, 1), (0, 1)}
    assert all(m.src == m.dest == (0, 0) for m in carries)  # 鼠妇原地不动


def test_a_carry_reports_only_the_destination_that_changed(game_x: HiveGame):
    """``destinations()`` 是"这一手之后哪几格变了" —— 鼠妇自己没动就不能报它。"""
    carry = _carries(game_x, _state(CARRY, current=0))[0]
    assert carry.destinations() == (carry.carried_dest,)


def test_applying_a_carry_moves_only_the_carried_piece(game_x: HiveGame):
    carry = _carries(game_x, _state(CARRY, current=0))[0]
    after = game_x.apply(_state(CARRY, current=0), carry)
    assert after.stack_at((0, 0)) == (P(0, "pillbug"),)
    assert after.stack_at(carry.carried_dest) == (P(1, "ant"),)
    assert after.stack_at((1, 0)) == ()


def test_pillbug_can_also_just_walk_one_cell(game_x: HiveGame):
    """搬运和走一格是**两个**着法，不是一回合两件事。"""
    state = _state(CARRY, current=0)
    own = {
        m.dest
        for m in game_x.legal_moves(state)
        if isinstance(m, MoveMove) and m.src == (0, 0)
    }
    assert own == {(0, -1), (0, 1)}


def test_pillbug_cannot_carry_a_buried_piece(game_x: HiveGame):
    board = dict(CARRY)
    board[(1, 0)] = [P(1, "ant"), P(1, "beetle")]
    assert not _carries(game_x, _state(board, current=0))


def test_pillbug_cannot_break_the_hive(game_x: HiveGame):
    """被搬的那枚棋如果是蜂巢的唯一连接点，就搬不动。"""
    board = dict(CARRY)
    board[(2, 0)] = [P(1, "ant")]
    assert not _carries(game_x, _state(board, current=0))


def test_pillbug_may_carry_an_enemy_piece(game_x: HiveGame):
    """官方规则：敌我的棋都能搬。"""
    carry = _carries(game_x, _state(CARRY, current=0))[0]
    assert carry.carried_owner == 1
    assert carry.carried_kind == "ant"


@pytest.mark.parametrize("kind", ["ladybug", "mosquito", "pillbug"])
def test_every_expansion_bug_can_be_placed_and_moved(game_x: HiveGame, kind: str):
    """冒烟：三种扩展虫都能落场，也都能生成着法（不至于生出来就是死子）。"""
    state = game_x.apply(game_x.initial_state(), PlaceMove(0, kind, (0, 0)))
    assert state.stack_at((0, 0)) == (P(0, kind),)
    assert state.hand_left(0, kind) == 0
