"""``apply`` 的不可变性、子数守恒、终局与哈希。"""

from __future__ import annotations

import dataclasses

import pytest
from aba_helpers import make_state, parse

from boardgames.games.abalone.geometry import CELLS, INDEX
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState

E, NE, NW, W, SW, SE = range(6)


def _move_to(game, state, group, direction):
    return next(
        m
        for m in game.legal_moves(state)
        if m.cells == tuple(sorted(group)) and m.direction == direction
    )


def test_apply_does_not_mutate_the_input(game, standard):
    before = standard.cells
    move = game.legal_moves(standard)[0]
    game.apply(standard, move)
    assert standard.cells is before
    assert standard.ply == 0


def test_apply_advances_player_and_ply(game, standard):
    move = game.legal_moves(standard)[0]
    after = game.apply(standard, move)
    assert after.current == 1 - standard.current
    assert after.ply == standard.ply + 1
    assert after is not standard


def test_marble_count_is_conserved(game, standard):
    """盘上剩的子 + 双方挤出去的总数，恒等于 28。"""
    state = standard
    for _ in range(60):
        if state.is_terminal():
            break
        state = game.apply(state, game.legal_moves(state)[0])
    on_board = sum(state.marble_count())
    assert on_board + state.out[0] + state.out[1] == 28


def test_plain_move_shifts_the_group(game):
    state = make_state({(0, 0): 1, (1, 0): 1, (-2, -2): 2}, current=0)
    after = game.apply(state, _move_to(game, state, [(0, 0), (1, 0)], SE))
    assert after.at((0, 1)) == 1 and after.at((1, 1)) == 1
    assert after.at((0, 0)) == 0 and after.at((1, 0)) == 0


def test_push_shifts_both_groups(game):
    """2 推 1：双方的两组都整体前进一格，被推的那枚仍留在盘上。"""
    state = make_state({(0, 0): 1, (1, 0): 1, (2, 0): 2, (-4, 0): 2}, current=0)
    after = game.apply(state, _move_to(game, state, [(0, 0), (1, 0)], E))
    assert after.at((1, 0)) == 1 and after.at((2, 0)) == 1
    assert after.at((3, 0)) == 2, "被推的那一枚应该前进一格"
    assert after.out == (0, 0)


def test_ejection_removes_the_marble_and_scores(game):
    """边界上的推挤 = 挤出：对方那枚从棋盘上消失，己方最前一枚补进那个格子。

    注意 **(4, 0) 最终是 1 而不是 0** —— 沿 E 方向 ``r=0`` 行的最后一格就是 ``q=4``，
    被推的那枚越过外沿出界后，我方压上来的第二枚正好落在它原来的位置上。
    只在对方占位位置上少写了一枚背景子也是不行的：被推空的那一方若**整方清零**，
    :meth:`~boardgames.games.abalone.state.AbaloneState.is_terminal` 会按"行棋方
    无子可动"判终局（防御性条款，见该方法注释），这里就没法验证"还没结束"了。
    """
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2, (-4, 4): 1, (0, -4): 2}, current=0)
    after = game.apply(state, _move_to(game, state, [(2, 0), (3, 0)], E))
    assert after.at((2, 0)) == 0, "队尾必须让出原来的格子"
    assert after.at((3, 0)) == 1 and after.at((4, 0)) == 1, "我方两枚整体前进一格"
    assert after.out == (1, 0)
    assert after.marble_count() == (3, 1), "被挤出的那一枚必须从棋盘上消失"
    assert not after.is_terminal()


def test_sixth_ejection_ends_the_game(game):
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0), current=0)
    after = game.apply(state, _move_to(game, state, [(2, 0), (3, 0)], E))
    assert after.out == (6, 0)
    assert after.is_terminal()
    assert after.winner() == 0, "winner 必须是玩家索引 0/1，不是棋子值 1/2"


def test_out_belongs_to_the_pusher_not_the_victim(game):
    """``out[p]`` 记的是 **p 把对手推出去的子数**，不是 p 自己掉了几枚。

    记反了会让胜负判定的符号整个反过来（赢家变成被推光的一方）。
    """
    push = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(0, 5), current=0)
    after = game.apply(push, _move_to(game, push, [(2, 0), (3, 0)], E))
    assert after.out == (1, 5), "+1 的是推出方的那一栏"
    assert after.winner() is None, "P1 才挤出 5 枚，还没到 6，胜负未分"

    sixth = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0), current=0)
    terminal = game.apply(sixth, _move_to(game, sixth, [(2, 0), (3, 0)], E))
    assert terminal.winner() == 0
    assert terminal.out[terminal.winner()] == 6, "赢家是把对手推掉 6 枚的那个"


def test_illegal_move_raises(game, standard):
    from boardgames.games.abalone.move import AbaloneMove

    with pytest.raises(ValueError):
        game.apply(standard, AbaloneMove(0, ((0, 0),), E))


def test_zobrist_depends_on_board_and_player_but_not_on_ply(game):
    state = make_state({(0, 0): 1, (1, 0): 1}, current=0, ply=3)
    same = make_state({(0, 0): 1, (1, 0): 1}, current=0, ply=99)
    other_turn = make_state({(0, 0): 1, (1, 0): 1}, current=1)
    moved = game.apply(state, _move_to(game, state, [(0, 0), (1, 0)], SE))
    assert state.zobrist_hash() == same.zobrist_hash()
    assert state.zobrist_hash() != other_turn.zobrist_hash()
    assert state.zobrist_hash() != moved.zobrist_hash()


def test_out_is_derivable_from_the_board(game, standard):
    """``zobrist_hash`` 排除 ``out`` 的依据：``out`` 与盘面一一对应。"""
    state = standard
    for _ in range(40):
        if state.is_terminal():
            break
        state = game.apply(state, game.legal_moves(state)[0])
    on_p0, on_p1 = state.marble_count()
    assert state.out == (14 - on_p1, 14 - on_p0)


@pytest.mark.parametrize("setup", ["standard", "belgian_daisy", "german_daisy"])
def test_initial_state_has_no_duplicate_coordinates(game, setup):
    state = AbaloneGame(setup).initial_state()
    occupied = [CELLS[i] for i, v in enumerate(state.cells) if v]
    assert len(occupied) == len(set(occupied)) == 28
    assert all(pos in INDEX for pos in occupied)


def test_standard_ascii_parses_back_to_the_same_state():
    rows = [
        "OOOOO",
        "OOOOOO",
        "..OOO..",
        "........",
        ".........",
        "........",
        "..XXX..",
        "XXXXXX",
        "XXXXX",
    ]
    assert parse(rows).cells == AbaloneGame("standard").initial_state().cells


def test_state_is_hashable_and_frozen(standard):
    assert isinstance(hash(standard), int)
    with pytest.raises(dataclasses.FrozenInstanceError):
        standard.ply = 5  # type: ignore[misc]


def test_ordinary_position_is_not_terminal():
    state = AbaloneState(cells=(0,) * 61, out=(0, 0), current=0, ply=0)
    state = make_state({(0, 0): 1, (1, 0): 2})
    assert state.winner() is None
    assert not state.is_terminal()


def test_a_side_with_no_marbles_left_is_terminal():
    """防御性条款：行棋方在盘上一枚子都不剩 → 终局。

    正常对局（28 枚守恒）轮不到这条，但少了它 MCTS 的 rollout 会在
    "非终局且无处可走"的节点上空转到 cap 或直接抛错（AI 线程吞掉异常，
    表现为 AI 突然不下棋）。
    """
    state = make_state({(0, 0): 1}, current=1)
    assert state.marble_count() == (1, 0)
    assert state.is_terminal()
    # 判终局但**不**自作主张判胜：out 没到 6，winner 保持 None
    assert state.winner() is None
    assert state.out == (0, 0)
