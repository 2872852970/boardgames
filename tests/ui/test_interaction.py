"""新版交互：放墙提示的边界规则、固定双方信息、数值直接输入。"""

from __future__ import annotations

import pygame
from helpers import (
    clear_input as _clear_input,
)
from helpers import (
    key_event as _key,
)
from helpers import (
    pos_for as _pos_for,
)
from helpers import (
    press as _press,
)
from helpers import (
    type_text as _type_text,
)
from helpers import (
    visible_slider as _visible_slider,
)

# --------------------------------------------------------------------------- #
# 放墙提示：4 格交点处不提示
# --------------------------------------------------------------------------- #

def test_no_wall_hint_at_grid_corner(make_window):
    """四个格子的公共点：横竖说不清，不提示放墙（这里以前会随鼠标抖动）。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view

    corners = ((4.0, 4.0), (4.03, 4.0), (4.0, 3.97), (3.96, 4.02))
    for fx, fy in corners:
        view.handle_motion(_pos_for(window, fx, fy), session.game, session.state, window.view_state)
        assert view._hover_wall is None, f"交点 ({fx}, {fy}) 不该提示放墙"
        assert view._hover_kind != "wall"


def test_wall_hint_appears_off_corner(make_window):
    """稍微离开交点、贴住某一条边，就应该给出提示。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view

    view.handle_motion(_pos_for(window, 4.4, 4.0), session.game, session.state, window.view_state)
    assert view._hover_wall == ("h", 3, 3)

    view.handle_motion(_pos_for(window, 4.0, 4.4), session.game, session.state, window.view_state)
    assert view._hover_wall == ("v", 3, 3)


def test_no_orientation_flicker_along_one_edge(make_window):
    """沿一条边扫过鼠标时，朝向不能来回跳（只会是横墙或"无提示"）。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view

    seen: list[str | None] = []
    x = 3.6
    while x <= 4.4:
        view.handle_motion(_pos_for(window, x, 4.0), session.game, session.state, window.view_state)
        seen.append(view._hover_wall[0] if view._hover_wall else None)
        x += 0.02

    assert "v" not in seen, f"沿水平边扫过时冒出了竖墙提示: {seen}"
    assert None in seen, "交点附近应当有一段不提示的静默带"
    # 朝向最多切换 2 次（无提示 → 横墙 → 无提示 → 横墙 → 无提示）
    switches = sum(1 for a, b in zip(seen, seen[1:], strict=False) if a != b)
    assert switches <= 4, f"朝向切换过于频繁（{switches} 次）: {seen}"


def test_no_wall_hint_right_after_placing(make_window):
    """刚放完墙的位置不再重复提示；鼠标挪开一格后恢复提示。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view
    pos = _pos_for(window, 4.4, 4.0)

    view.handle_motion(pos, session.game, session.state, window.view_state)
    assert view._hover_wall == ("h", 3, 3)

    pygame.event.post(_press(pos))
    window._handle_events()
    assert len(session.history) == 2
    assert session.state.h_mask != 0

    # 鼠标没动：这里已经有墙了，不该再提示
    view.handle_motion(pos, session.game, session.state, window.view_state)
    assert view._hover_wall is None

    # 挪到下一格：恢复正常提示
    view.handle_motion(_pos_for(window, 4.4, 5.0), session.game, session.state, window.view_state)
    assert view._hover_wall == ("h", 3, 4)


# --------------------------------------------------------------------------- #
# 双方信息固定在头部，不随滚动隐藏
# --------------------------------------------------------------------------- #

def test_player_rows_are_pinned_above_scroll_area(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window._update(16.0)
    sidebar = window.sidebar

    before = sidebar._players_rect.copy()
    assert before.bottom <= sidebar.viewport.y, "双方信息应当位于滚动区之上"

    sidebar._scroll_by(600)
    window._update(16.0)
    assert sidebar._players_rect == before, "滚动不应移动双方信息"
    assert sidebar._players_rect.bottom <= sidebar.viewport.y

    sidebar.scroll = 0.0
    window._update(16.0)
    assert sidebar._players_rect == before


def test_player_rows_visible_in_pvp_too(make_window):
    """双人对战虽然没有"对局双方"分组，但双方信息仍然固定显示。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    assert window.sidebar._players_rect is not None
    assert window.sidebar._players_rect.bottom <= window.sidebar.viewport.y


# --------------------------------------------------------------------------- #
# 点击数值框直接输入
# --------------------------------------------------------------------------- #

def test_click_value_box_starts_editing(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")
    assert not slider.editing

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    assert slider.editing
    assert slider._buffer == "4"  # 进入编辑时带入当前值


def test_type_number_and_confirm(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type_text(window, "7")
    window.sidebar.handle_key(_key(pygame.K_RETURN))

    assert not slider.editing
    assert slider.value == 7
    assert window.settings.get("minimax_depth") == 7


def test_escape_cancels_typing(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")
    before = slider.value

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type_text(window, "9")
    window.sidebar.handle_key(_key(pygame.K_ESCAPE))

    assert not slider.editing
    assert slider.value == before
    assert window.settings.get("minimax_depth") == before


def test_typed_value_is_clamped_to_spec_range(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type_text(window, "999")
    window.sidebar.handle_key(_key(pygame.K_RETURN))

    assert slider.value == slider.maximum
    assert window.settings.get("minimax_depth") == slider.maximum


def test_backspace_works(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type_text(window, "12")
    window.sidebar.handle_key(_key(pygame.K_BACKSPACE))  # 删掉行尾的 2 → "1"
    window.sidebar.handle_key(_key(pygame.K_RETURN))
    assert slider.value == 1


def test_hotkeys_are_suppressed_while_editing(make_window):
    """编辑数值时，键盘不能再去触发新局 / 悔棋 / 退出。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    assert slider.editing

    before = len(window.session.history)
    pygame.event.post(_key(pygame.K_n, "n"))  # 新局
    window._handle_events()
    assert len(window.session.history) == before, "编辑时不该触发新局"

    pygame.event.post(_key(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is True, "编辑时按 Esc 只应该结束编辑，不应该退出"
    assert not slider.editing


def test_clicking_elsewhere_commits_input(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type_text(window, "8")

    pygame.event.post(_press((5, 5)))  # 点棋盘空白处
    window._handle_events()

    assert not slider.editing
    assert window.settings.get("minimax_depth") == 8
    assert len(window.session.history) == 1, "结束编辑的这一次点击不应顺手落子"


def test_drag_still_works_after_adding_input_box(make_window):
    """加了输入框之后，拖滑轨仍然要正常。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    from helpers import motion as _motion
    from helpers import release as _release

    pygame.event.post(_press((slider.rect.x + 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(_motion((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(_release((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()

    assert slider.value == slider.maximum
    assert not slider.editing
