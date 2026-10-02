"""放墙合法性：边界、重叠、交叉、L/T 接触、墙数耗尽。"""

from __future__ import annotations

from boardgames.games.quoridor.geometry import HORIZONTAL, VERTICAL


def test_anchor_out_of_range_is_illegal(game, make_state):
    st = make_state()
    assert game.is_wall_legal(st, 0, (HORIZONTAL, -1, 0)) is False
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 8, 0)) is False  # size=9 → w=8，锚点 0..7
    assert game.is_wall_legal(st, 0, (VERTICAL, 0, 8)) is False


def test_no_walls_left_is_illegal(game, make_state):
    st = make_state(walls=(0, 10))
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 3, 3)) is False
    assert game.all_legal_walls(st, 0) == []
    # 墙用尽后只剩走子
    moves = game.legal_moves(st)
    assert moves and all(not hasattr(m, "orient") for m in moves)


def test_same_anchor_is_illegal(game, make_state):
    st = make_state(h=((3, 3),))
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 3, 3)) is False


def test_adjacent_same_orientation_overlaps(game, make_state):
    """同向左右相邻锚点共享一段边 → 重叠，非法。"""
    st = make_state(h=((3, 3),))
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 2, 3)) is False
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 4, 3)) is False
    # 隔一格则不相邻 → 合法
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 5, 3)) is True


def test_adjacent_vertical_overlaps(game, make_state):
    st = make_state(v=((3, 3),))
    assert game.is_wall_legal(st, 0, (VERTICAL, 3, 2)) is False
    assert game.is_wall_legal(st, 0, (VERTICAL, 3, 4)) is False
    assert game.is_wall_legal(st, 0, (VERTICAL, 3, 5)) is True


def test_crossing_at_same_anchor_is_illegal(game, make_state):
    """同锚点横竖墙成"十"字 → 交叉，非法（严格规则默认）。"""
    st = make_state(v=((3, 3),))
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 3, 3)) is False

    st2 = make_state(h=((3, 3),))
    assert game.is_wall_legal(st2, 0, (VERTICAL, 3, 3)) is False


def test_crossing_can_be_enabled(make_state):
    """可选放开交叉限制（配置项），默认关闭。"""
    from boardgames.games.quoridor.rules import QuoridorGame

    relaxed = QuoridorGame(allow_wall_crossing=True)
    st = make_state(v=((3, 3),))
    assert relaxed.is_wall_legal(st, 0, (HORIZONTAL, 3, 3)) is True


def test_l_and_t_contact_is_legal(game, make_state):
    """端点相接的 L / T 形合法 —— 用边网格判断会误判，这里锁定锚点语义。"""
    # 竖墙在 (3,3)：占据竖直网格线 x=4、y∈[3,5]
    st = make_state(v=((3, 3),))
    # 横墙在 (4,3)：占据水平网格线 y=4、x∈[4,6]，与竖墙只在端点 (4,4) 相接 → T 形，合法
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 4, 3)) is True
    # 横墙在 (2,3)：占据 y=4、x∈[2,4]，与竖墙也在 (4,4) 端点相接 → 合法
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 2, 3)) is True


def test_initial_legal_wall_count(game, make_state):
    """9x9 空棋盘：8x8 锚点 × 2 朝向 = 128。"""
    st = make_state()
    assert len(game.all_legal_walls(st, 0)) == 128


def test_illegal_move_is_rejected(game, make_state):
    st = make_state()
    from boardgames.games.quoridor.move import WallMove

    # 越界墙
    assert game.is_legal(st, WallMove(HORIZONTAL, 8, 0)) is False
