"""BFS 最短路径、边派生与放墙的连通性校验。"""

from __future__ import annotations

from boardgames.games.quoridor import geometry as geo
from boardgames.games.quoridor.geometry import HORIZONTAL, VERTICAL


def test_open_board_distances(game, make_state):
    st = make_state()
    assert geo.shortest_path(st.size, st.h_mask, st.v_mask, (4, 8), 0) == 8
    assert geo.shortest_path(st.size, st.h_mask, st.v_mask, (4, 0), 8) == 8
    assert geo.shortest_path(st.size, st.h_mask, st.v_mask, (4, 0), 0) == 0  # 已在目标行


def test_wall_increases_distance(game, make_state):
    st = make_state(h=((3, 3),))
    # 水平墙 (3,3) 阻断 (3,3)-(3,4) 与 (4,3)-(4,4)，玩家 0 需绕行
    assert geo.blocked_vertical(st.size, st.h_mask, 3, 3) is True
    assert geo.blocked_vertical(st.size, st.h_mask, 4, 3) is True
    assert geo.blocked_vertical(st.size, st.h_mask, 5, 3) is False


def test_horizontal_edge_derivation_from_vertical_wall(game, make_state):
    st = make_state(v=((3, 3),))
    # 垂直墙 (3,3) 阻断 (3,3)-(4,3) 与 (3,4)-(4,4)
    assert geo.blocked_horizontal(st.size, st.v_mask, 3, 3) is True
    assert geo.blocked_horizontal(st.size, st.v_mask, 3, 4) is True
    assert geo.blocked_horizontal(st.size, st.v_mask, 3, 2) is False
    assert geo.blocked_horizontal(st.size, st.v_mask, 4, 3) is False


def test_edge_off_by_one_at_borders(game, make_state):
    """边界处的边由最后一个锚点覆盖（最容易 off-by-one 的地方）。"""
    st = make_state(h=((7, 0),))
    # 锚点 (7,0) 覆盖 hv 边 (7,0) 与 (8,0)
    assert geo.blocked_vertical(st.size, st.h_mask, 7, 0) is True
    assert geo.blocked_vertical(st.size, st.h_mask, 8, 0) is True
    assert geo.blocked_vertical(st.size, st.h_mask, 6, 0) is False


def test_sealing_opponent_is_illegal(game, make_state):
    """能把对手彻底封死的墙 → 非法。

    3x3 棋盘：玩家 1 在 (0,1)，四周被 (0,0) 横墙（封上）、(0,0) 竖墙（封右）夹住，
    再由候选墙 (0,1) 封住下方 → 完整封死。
    """
    st = make_state(size=3, p0=(2, 2), p1=(0, 1), h=((0, 0),), v=((0, 0),), current=0)
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 0, 1)) is False


def test_sealing_self_is_illegal(game, make_state):
    """把自己封死同样非法（连通性必须对双方各查一次）。"""
    st = make_state(size=3, p0=(0, 1), p1=(1, 0), h=((0, 0),), v=((0, 0),), current=0)
    assert game.is_wall_legal(st, 0, (HORIZONTAL, 0, 1)) is False


def test_keeping_one_path_is_legal(game, make_state):
    """只留一条路 → 合法。"""
    st = make_state()
    # 在空棋盘上随便放一面墙，双方都还能绕行
    assert game.is_wall_legal(st, 0, (VERTICAL, 3, 3)) is True


def test_shortest_path_cells_is_contiguous(make_state):
    st = make_state(h=((3, 3),))
    path = geo.shortest_path_cells(st.size, st.h_mask, st.v_mask, (4, 8), 0)
    assert path is not None and path[0] == (4, 8) and path[-1][1] == 0
    assert len(path) - 1 == geo.shortest_path(st.size, st.h_mask, st.v_mask, (4, 8), 0)
    for a, b in zip(path, path[1:], strict=False):
        assert geo.can_step(st.size, st.h_mask, st.v_mask, a, b)


def test_anchors_blocking_step(game, make_state):
    st = make_state()
    # 从 (4,4) 向下走的边，可由水平墙锚点 (4,4) 或 (3,4) 阻断
    assert set(geo.anchors_blocking_step(st.size, (4, 4), (4, 5))) == {
        (HORIZONTAL, 3, 4),
        (HORIZONTAL, 4, 4),
    }
    # 从 (4,4) 向右走的边，可由垂直墙锚点 (4,4) 或 (4,3) 阻断
    assert set(geo.anchors_blocking_step(st.size, (4, 4), (5, 4))) == {
        (VERTICAL, 4, 3),
        (VERTICAL, 4, 4),
    }
