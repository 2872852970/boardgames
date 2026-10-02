"""跳跃规则全分支。"""

from __future__ import annotations

from boardgames.games.quoridor.move import PawnMove


def dsts(moves, src):
    return {m.dst for m in moves if isinstance(m, PawnMove) and m.src == src}


def test_straight_jump_when_cell_behind_is_free(game, make_state):
    """面对面且正后方空 → 直跳，且不再生成斜跳（互斥）。"""
    st = make_state(p0=(4, 5), p1=(4, 4), current=0)
    moves = game.pawn_moves_for(st, 0)
    d = dsts(moves, (4, 5))
    assert (4, 3) in d
    assert (3, 4) not in d and (5, 4) not in d
    assert (4, 4) not in d  # 不能走到对手格上


def test_diagonal_jump_when_straight_blocked_by_wall(game, make_state):
    """正后方被墙挡 → 斜跳到左右两侧。"""
    st = make_state(p0=(4, 5), p1=(4, 4), h=((3, 3),), current=0)
    # 水平墙 (3,3) 覆盖 hv 边 (3,3),(4,3)，其中 (4,3) 正是直跳落点前的边
    d = dsts(game.pawn_moves_for(st, 0), (4, 5))
    assert (4, 3) not in d
    assert (3, 4) in d and (5, 4) in d


def test_diagonal_jump_only_one_side_open(game, make_state):
    """两侧斜向独立判定：一侧被墙挡，只剩另一侧。"""
    st = make_state(p0=(4, 5), p1=(4, 4), h=((3, 3),), v=((4, 4),), current=0)
    # 垂直墙 (4,4) 覆盖 hh 边 (4,4),(4,5)，阻断 (4,4)->(5,4) 这条绕行边
    d = dsts(game.pawn_moves_for(st, 0), (4, 5))
    assert (3, 4) in d
    assert (5, 4) not in d


def test_diagonal_jump_when_straight_is_off_board(game, make_state):
    """对手贴着边线，正后方越界 → 只能斜跳。"""
    st = make_state(p0=(4, 1), p1=(4, 0), current=0)
    d = dsts(game.pawn_moves_for(st, 0), (4, 1))
    assert (3, 0) in d and (5, 0) in d
    assert (4, -1) not in d


def test_diagonal_jump_at_corner_excludes_off_board(game, make_state):
    """角落处只有一个斜向在界内。"""
    st = make_state(p0=(0, 1), p1=(0, 0), current=0)
    d = dsts(game.pawn_moves_for(st, 0), (0, 1))
    assert (1, 0) in d
    assert (-1, 0) not in d


def test_no_jump_when_not_adjacent(game, make_state):
    """中间隔一格不是"面对面"，只能普通移动，不能跳。"""
    st = make_state(p0=(4, 5), p1=(4, 3), current=0)
    d = dsts(game.pawn_moves_for(st, 0), (4, 5))
    assert (4, 4) in d
    assert (4, 2) not in d


def test_cannot_jump_over_wall_in_front(game, make_state):
    """连对手那一格都过不去时，不能跳。"""
    st = make_state(p0=(4, 5), p1=(4, 4), h=((3, 4),), current=0)
    # 水平墙 (3,4) 覆盖 hv 边 (3,4),(4,4)，阻断 (4,4)->(4,5)
    d = dsts(game.pawn_moves_for(st, 0), (4, 5))
    for blocked in ((4, 4), (4, 3), (3, 4), (5, 4)):
        assert blocked not in d
    # 其余三个正常方向仍然可走
    assert d == {(4, 6), (3, 5), (5, 5)}


def test_jump_moves_are_legal(game, make_state):
    """生成的跳法必须通过 is_legal。"""
    st = make_state(p0=(4, 5), p1=(4, 4), h=((3, 3),), current=0)
    for m in game.pawn_moves_for(st, 0):
        assert game.is_legal(st, m)
