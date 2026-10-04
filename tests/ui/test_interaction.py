"""新版交互测试：右键开关放墙、朝向滞回、固定双方信息、数值直接输入、自对弈单步。"""

from __future__ import annotations

import time

import pygame
from helpers import clear_input, key_event, pos_for, press, release, type_text, visible_slider

from boardgames.games.quoridor.view import WALL_MODE_KEY


def _wall_mode(window, on: bool = True) -> None:
    window.view_state.extra[WALL_MODE_KEY] = on


# --------------------------------------------------------------------------- #
# 右键开关放墙模式
# --------------------------------------------------------------------------- #

def test_right_click_toggles_wall_mode(make_window):
    window = make_window(mode="pvp")
    pos = pos_for(window, 4.5, 4.5)
    assert not window.view_state.extra.get(WALL_MODE_KEY, False)

    pygame.event.post(press(pos, button=3))
    window._handle_events()
    assert window.view_state.extra[WALL_MODE_KEY] is True

    pygame.event.post(press(pos, button=3))
    window._handle_events()
    assert window.view_state.extra[WALL_MODE_KEY] is False


def test_right_click_ignored_when_ai_is_playing(make_window):
    """自对弈时没有人类的回合，右键不该能进放墙模式。"""
    window = make_window(mode="eve", p1_type="minimax", p2_type="minimax")
    pygame.event.post(press(pos_for(window, 4.5, 4.5), button=3))
    window._handle_events()
    assert not window.view_state.extra.get(WALL_MODE_KEY, False)


def test_escape_leaves_wall_mode_before_quitting(make_window):
    """Esc 是三级的：退放墙模式 → 回大厅 → （在大厅里）退出程序。"""
    window = make_window(mode="pvp")
    _wall_mode(window)

    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is True, "Esc 应当先退出放墙模式，而不是回大厅"
    assert window.view_state.extra[WALL_MODE_KEY] is False

    # 没有放墙模式时，Esc 回到大厅（而不是直接退出程序）
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is True
    assert window.scene is window.lobby, "Esc 应当回到游戏选择大厅"

    # 大厅里再按 Esc 才真正退出
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is False


# --------------------------------------------------------------------------- #
# 交点也提示，但朝向不能抖
# --------------------------------------------------------------------------- #

def test_wall_hint_at_grid_corner(make_window):
    """四个格子的公共交点也要给出提示。"""
    window = make_window(mode="pvp")
    session = window.session
    _wall_mode(window)
    window.view.handle_motion(
        pos_for(window, 4.0, 4.0), session.game, session.state, window.view_state
    )
    assert window.view._hover_wall is not None
    assert window.view._hover_kind == "wall"


def test_orientation_stable_with_tiny_jitter(make_window):
    """在交点附近轻微抖动鼠标，横 / 竖朝向必须保持不变。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view
    _wall_mode(window)

    seen: set[str] = set()
    for delta in (0.0, 0.03, -0.02, 0.04, -0.03, 0.01, 0.02, -0.01, 0.0):
        view.handle_motion(
            pos_for(window, 4.0 + delta, 4.0 - delta), session.game, session.state, window.view_state
        )
        assert view._hover_wall is not None
        seen.add(view._hover_wall[0])
    assert len(seen) == 1, f"交点附近轻微抖动就换了朝向: {seen}"


def test_orientation_follows_deliberate_move(make_window):
    """但明确朝另一条网格线移动时，朝向要能跟着换过去。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view
    _wall_mode(window)

    view.handle_motion(pos_for(window, 4.30, 4.0), session.game, session.state, window.view_state)
    assert view._hover_wall[0] == "h"

    view.handle_motion(pos_for(window, 4.0, 4.30), session.game, session.state, window.view_state)
    assert view._hover_wall[0] == "v"


def test_v_key_flips_orientation(make_window):
    window = make_window(mode="pvp")
    session = window.session
    view = window.view
    _wall_mode(window)
    view.handle_motion(pos_for(window, 4.0, 4.0), session.game, session.state, window.view_state)
    before = view._hover_wall[0]

    pygame.event.post(key_event(pygame.K_v))
    window._handle_events()

    assert view._hover_wall[0] != before
    assert view._hover_wall[1:] == (3, 3)  # 还是同一个交点


def test_no_wall_hint_right_after_placing(make_window):
    """刚放完墙的位置不再重复提示；挪开一格后恢复，且放完会自动退出放墙模式。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view
    pos = pos_for(window, 4.4, 4.0)

    _wall_mode(window)
    view.handle_motion(pos, session.game, session.state, window.view_state)
    assert view._hover_wall == ("h", 3, 3)

    pygame.event.post(press(pos))
    window._handle_events()
    assert len(session.history) == 2
    assert window.view_state.extra[WALL_MODE_KEY] is False, "放完墙应当自动退出放墙模式"

    _wall_mode(window)
    view.handle_motion(pos, session.game, session.state, window.view_state)
    assert view._hover_wall is None, "刚放下的墙不该再提示"

    view.handle_motion(pos_for(window, 4.4, 5.0), session.game, session.state, window.view_state)
    assert view._hover_wall is not None, "挪开一格后应恢复正常提示"


def test_pawn_hints_hidden_in_wall_mode(make_window):
    """放墙模式下不显示走子落点，避免和幽灵墙混淆。"""
    window = make_window(mode="pvp")
    session = window.session
    view = window.view

    view.handle_motion(pos_for(window, 4.5, 7.5), session.game, session.state, window.view_state)
    assert view._hover_target == (4, 7)

    _wall_mode(window)
    view.handle_motion(pos_for(window, 4.5, 7.5), session.game, session.state, window.view_state)
    assert view._hover_target is None


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
    slider = visible_slider(window, "walls_per_player")
    assert not slider.editing

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    assert slider.editing
    assert slider._buffer == "10"  # 进入编辑时带入当前值（每人墙数默认 10）


def test_type_number_and_confirm(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    clear_input(window)
    type_text(window, "7")
    window.sidebar.handle_key(key_event(pygame.K_RETURN))

    assert not slider.editing
    assert slider.value == 7
    assert window.settings.get("walls_per_player") == 7


def test_escape_cancels_typing(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")
    before = slider.value

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    clear_input(window)
    type_text(window, "9")
    window.sidebar.handle_key(key_event(pygame.K_ESCAPE))

    assert not slider.editing
    assert slider.value == before
    assert window.settings.get("walls_per_player") == before


def test_typed_value_is_clamped_to_spec_range(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    clear_input(window)
    type_text(window, "999")
    window.sidebar.handle_key(key_event(pygame.K_RETURN))

    assert slider.value == slider.maximum
    assert window.settings.get("walls_per_player") == slider.maximum


def test_backspace_works(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    clear_input(window)
    type_text(window, "12")
    window.sidebar.handle_key(key_event(pygame.K_BACKSPACE))  # 删掉行尾的 2 → "1"
    window.sidebar.handle_key(key_event(pygame.K_RETURN))
    assert slider.value == 1


def test_hotkeys_are_suppressed_while_editing(make_window):
    """编辑数值时，键盘不能再去触发新局 / 悔棋 / 退出。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    assert slider.editing

    before = len(window.session.history)
    pygame.event.post(key_event(pygame.K_n, "n"))  # 新局
    window._handle_events()
    assert len(window.session.history) == before, "编辑时不该触发新局"

    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is True, "编辑时按 Esc 只应该结束编辑，不应该退出"
    assert not slider.editing


def test_clicking_elsewhere_commits_input(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    clear_input(window)
    type_text(window, "8")

    pygame.event.post(press((5, 5)))  # 点棋盘空白处
    window._handle_events()

    assert not slider.editing
    assert window.settings.get("walls_per_player") == 8
    assert len(window.session.history) == 1, "结束编辑的这一次点击不应顺手落子"


def test_drag_still_works_after_adding_input_box(make_window):
    """加了输入框之后，拖滑轨仍然要正常。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = visible_slider(window, "walls_per_player")

    pygame.event.post(press((slider.rect.x + 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION,
        {"pos": (slider.rect.right - 4, slider.rect.y + 34), "rel": (0, 0), "buttons": (1, 0, 0)},
    ))
    window._handle_events()
    pygame.event.post(release((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()

    assert slider.value == slider.maximum
    assert not slider.editing


# --------------------------------------------------------------------------- #
# AI 自对弈：默认暂停 + 鼠标单步
# --------------------------------------------------------------------------- #

def _eve_window(make_window, **extra):
    return make_window(
        mode="eve",
        p1_type="minimax",
        p2_type="minimax",
        minimax_depth=1,
        minimax_time_ms=150,
        ai_delay_ms=0,
        anim_ms=0,
        **extra,
    )


def _run_until(window, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window._update(16.0)
        if predicate():
            return True
        time.sleep(0.003)
    return False


def test_self_play_starts_paused(make_window):
    window = _eve_window(make_window)
    assert window.session.paused is True, "AI 自对弈应当默认暂停"

    for _ in range(40):
        window._update(16.0)
    assert len(window.session.history) == 1, "暂停状态下 AI 不应自己走棋"


def test_step_button_only_in_self_play_mode(make_window):
    eve = _eve_window(make_window)
    eve._update(16.0)
    labels = [b.label for b in eve.sidebar._visible_footer()]
    assert "单步" in labels and "暂停" in labels

    pvp = make_window(mode="pvp")
    pvp._update(16.0)
    labels = [b.label for b in pvp.sidebar._visible_footer()]
    assert "单步" not in labels and "暂停" not in labels


def test_single_step_advances_exactly_one_ply(make_window):
    window = _eve_window(make_window)
    session = window.session

    assert session.request_step() is True
    assert _run_until(window, lambda: len(session.history) > 1), "单步没有落子"
    assert len(session.history) == 2
    assert session.paused is True, "单步之后应当仍然保持暂停"

    # 再跑一会儿不应该继续推进
    for _ in range(40):
        window._update(16.0)
    assert len(session.history) == 2


def test_clicking_board_single_steps(make_window):
    window = _eve_window(make_window)
    session = window.session

    pygame.event.post(press(pos_for(window, 4.5, 4.5)))
    window._handle_events()
    assert session.stepping is True

    assert _run_until(window, lambda: len(session.history) > 1), "点棋盘没有推进"
    assert len(session.history) == 2


def test_unpausing_runs_continuously(make_window):
    window = _eve_window(make_window)
    session = window.session
    session.paused = False

    assert _run_until(window, lambda: len(session.history) > 3), "取消暂停后 AI 没有连续走棋"
