"""点格棋视图：鼠标 ↔ 格线 的对应关系（渲染 + 命中）。

这类 bug 用"断言数据结构"是抓不到的 —— 一定要**画一帧再取像素**，
再配合"鼠标落在线上，命中的就必须是这条线"。

守三件事：

* 棋盘内**处处**都能命中一条边（没有"指着线却什么都不亮"的死区）；
* 命中的永远是**几何最近**的那条边，不存在整体偏移半格 / 错一格；
* 轮到玩家 2 时悬停预览照样亮（历史 bug：命中用的着法写死了 ``player=0``，
  而 ``Game.is_legal`` 会校验 ``move.player == state.current``）。
"""

from __future__ import annotations

import pygame
from helpers import motion, pos_for, press

from boardgames.games.dotsboxes import heuristic as heu
from boardgames.games.dotsboxes.move import EdgeMove
from boardgames.ui import theme

DB = "dotsboxes"


def _db_window(make_window, **overrides):
    window = make_window(game_key=DB, mode="pvp", **overrides)
    window._update(16.0)
    window._draw()
    return window


def _edges(view):
    """棋盘上所有边的 ``(orient, row, col)``。"""
    n = view.size
    for row in range(n):
        for col in range(n - 1):
            yield (0, row, col)
    for row in range(n - 1):
        for col in range(n):
            yield (1, row, col)


def _midpoint(view, orient, row, col):
    a, b = view._edge_segment(orient, row, col)
    return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)


# --------------------------------------------------------------------------- #
# 命中测试
# --------------------------------------------------------------------------- #

def test_every_edge_midpoint_hits_that_edge(make_window):
    window = _db_window(make_window)
    view = window.view
    for orient, row, col in _edges(view):
        assert view._edge_at(_midpoint(view, orient, row, col)) == (orient, row, col)


def test_no_dead_zone_inside_the_board(make_window):
    """棋盘内任意一点都能命中一条边 —— 这正是"鼠标和线差半格"的根治办法。"""
    window = _db_window(make_window)
    view = window.view
    cell = view.cell
    span = view.size - 1
    for i in range(0, 21):
        for j in range(0, 21):
            gx, gy = span * i / 20, span * j / 20
            pos = (int(view.origin[0] + gx * cell), int(view.origin[1] + gy * cell))
            assert view._edge_at(pos) is not None, f"棋盘内 ({gx:.2f}, {gy:.2f}) 没有命中任何边"


def test_hit_edge_is_the_geometrically_nearest_one(make_window):
    window = _db_window(make_window)
    view = window.view
    cell = view.cell
    for gx, gy in ((0.5, 0.5), (2.5, 3.5), (1.2, 4.8), (4.5, 0.2), (3.0, 2.0)):
        pos = (int(view.origin[0] + gx * cell), int(view.origin[1] + gy * cell))
        got = view._edge_at(pos)
        d_got = view._segment_distance(gx, gy, *got)
        d_best = min(view._segment_distance(gx, gy, *e) for e in _edges(view))
        assert d_got <= d_best + 0.03, f"({gx}, {gy}) 命中的不是最近的边"


def test_outside_the_board_hits_nothing(make_window):
    window = _db_window(make_window)
    view = window.view
    assert view._edge_at((0, 0)) is None
    assert view._edge_at((view.area.right + 50, view.area.bottom + 50)) is None


# --------------------------------------------------------------------------- #
# 悬停预览
# --------------------------------------------------------------------------- #

def _empty_edge(window, *, closes: bool | None = None):
    """挑一条还没画（且可选"会封口 / 不会封口"）的边。"""
    state = window.session.state
    for orient, row, col in _edges(window.view):
        drawn = (
            state.h_edges[state.h_index(row, col)]
            if orient == 0
            else state.v_edges[state.v_index(row, col)]
        )
        if drawn:
            continue
        closing = bool(heu.boxes_closed_by_move(state, orient, row, col))
        if closes is None or closing == closes:
            return (orient, row, col)
    raise AssertionError("找不到符合条件的空边")


def test_hover_preview_works_on_both_players_turns(make_window):
    """回归：轮到玩家 2 时预览必须照样亮（写死 ``player=0`` 会让它永远不亮）。"""
    window = _db_window(make_window)
    view, session = window.view, window.session
    orient, row, col = _empty_edge(window)
    pos = _midpoint(view, orient, row, col)

    assert session.state.current == 0
    view.handle_motion(pos, session.game, session.state, window.view_state)
    assert view._hover is not None and view._hover.player == 0

    # 换到玩家 2 走（随便画一条边就翻过去了）
    session.play(EdgeMove(*_empty_edge(window), 0))
    window._update(16.0)
    assert session.state.current == 1

    orient, row, col = _empty_edge(window)
    view.handle_motion(_midpoint(view, orient, row, col), session.game, session.state,
                       window.view_state)
    assert view._hover is not None, "轮到玩家 2 时预览不该是空的"
    assert view._hover.player == 1
    assert (view._hover.orient, view._hover.row, view._hover.col) == (orient, row, col)


def test_hover_on_a_drawn_edge_shows_nothing(make_window):
    """指到已经画过的边上：不预览（那条线已经在那儿了）。"""
    window = _db_window(make_window)
    view, session = window.view, window.session
    edge = _empty_edge(window)
    session.play(EdgeMove(*edge, 0))
    window._update(16.0)
    view.handle_motion(_midpoint(view, *edge), session.game, session.state, window.view_state)
    assert view._hover is None


def test_mouse_leaving_the_board_clears_the_preview(make_window):
    window = _db_window(make_window)
    view, session = window.view, window.session
    view.handle_motion(_midpoint(view, *_empty_edge(window)), session.game, session.state,
                       window.view_state)
    assert view._hover is not None
    # 鼠标移出棋盘区（场景会调这个可选钩子）
    pygame.event.post(motion((view.area.right + 40, view.area.bottom + 40)))
    window._handle_events()
    assert view._hover is None, "鼠标离开棋盘后还留着一条幽灵线"


def test_idle_hint_is_not_another_games_wording(make_window):
    """左上角胶囊的空闲文案不能写"投子"（那是四子棋的词）。"""
    window = _db_window(make_window)
    assert "投子" not in window.view.idle_hint()


# --------------------------------------------------------------------------- #
# 点击 → 落线（像素级）
# --------------------------------------------------------------------------- #

def test_clicked_edge_is_drawn_exactly_where_the_mouse_was(make_window):
    """鼠标点在哪条线上，线就画在哪条线上 —— 不许偏移半格（两个方向都测）。"""
    window = _db_window(make_window)
    view = window.view
    cell = view.cell
    player_color = theme.PLAYER_COLORS[0]

    for orient, row, col in ((0, 2, 1), (1, 2, 1), (0, 0, 0), (1, 4, 5)):
        window._restart()
        window._update(16.0)
        mid = _midpoint(view, orient, row, col)
        pygame.event.post(press(mid))
        window._handle_events()
        window._update(16.0)
        window._draw()

        state = window.session.state
        value = (
            state.h_edges[state.h_index(row, col)]
            if orient == 0
            else state.v_edges[state.v_index(row, col)]
        )
        assert value == 1, f"点击 ({orient}, {row}, {col}) 没把边画到这条线上"

        surface = window.screen
        drawn = surface.get_at(mid)[:3]
        assert all(abs(a - b) <= 24 for a, b in zip(drawn, player_color, strict=True)), (
            f"点击位置 ({orient}, {row}, {col}) 处没有画出这条边：{drawn}"
        )
        # 垂直方向偏移半格：那里不该有同样的线（防"划线整体差半格"）
        off = (mid[0], mid[1] + cell // 2) if orient == 0 else (mid[0] + cell // 2, mid[1])
        near = surface.get_at(off)[:3]
        assert not all(abs(a - b) <= 24 for a, b in zip(near, player_color, strict=True)), (
            f"半格之外 {off} 也画上了线 —— 划线位置整体偏了半格"
        )


def test_clicking_inside_a_cell_draws_the_nearest_edge(make_window):
    """格子正中间点击 → 画到最近的那条边上（不会有"点了没反应"）。"""
    window = _db_window(make_window)
    view, session = window.view, window.session
    cell = view.cell
    gx, gy = 3.5, 3.5
    pos = (int(view.origin[0] + gx * cell), int(view.origin[1] + gy * cell))
    expected = view._edge_at(pos)
    assert expected is not None

    pygame.event.post(press(pos))
    window._handle_events()
    orient, row, col = expected
    state = session.state
    value = (
        state.h_edges[state.h_index(row, col)]
        if orient == 0
        else state.v_edges[state.v_index(row, col)]
    )
    assert value == 1


def test_pawn_click_lands_on_an_adjacent_cell_not_half_a_cell_away(make_window):
    """鼠标落在两个点的中点上时，取的一定是这两个点之间的那条边。"""
    window = _db_window(make_window)
    view = window.view
    assert view._edge_at(pos_for(window, 2.5, 3.0)) == (0, 3, 2)
    assert view._edge_at(pos_for(window, 3.0, 2.5)) == (1, 2, 3)
