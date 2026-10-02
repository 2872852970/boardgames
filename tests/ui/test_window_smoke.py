"""无头 UI 冒烟测试：真正把窗口、交互、AI 串起来跑一遍。

使用 SDL 的 dummy 视频驱动，因此不需要真实显示器。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import time  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from boardgames.app import build_registry  # noqa: E402
from boardgames.settings import Settings  # noqa: E402
from boardgames.ui.window import GameWindow  # noqa: E402


@pytest.fixture
def make_window(tmp_path):
    created: list[GameWindow] = []

    def _make(**overrides) -> GameWindow:
        settings = Settings(tmp_path / "settings.json")
        for key, value in overrides.items():
            settings.values[key] = value
        window = GameWindow(settings, build_registry(), headless=True)
        created.append(window)
        return window

    yield _make
    for _window in created:
        if pygame.get_init():
            pygame.quit()


def test_window_runs_without_error(make_window):
    window = make_window(mode="pvp")
    window.run(max_frames=60)
    assert not pygame.get_init()  # run() 结束时会退出 pygame


def test_human_click_plays_a_move(make_window):
    window = make_window(mode="pvp")
    session = window.session
    target = session.game.pawn_moves_for(session.state, 0)[0].dst
    pos = window.view.cell_center(*target)

    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.pawns[0] == target
    assert session.state.current_player == 1


def test_click_outside_targets_is_ignored(make_window):
    window = make_window(mode="pvp")
    session = window.session
    pos = window.view.cell_center(0, 0)  # 开局时 (0,0) 不是合法落点
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()
    assert len(session.history) == 1


def _pos_for(window, fx: float, fy: float) -> tuple[int, int]:
    """把"格坐标"（可以是小数）换算成像素坐标。"""
    origin_x, origin_y = window.view.origin
    cell = window.view.cell
    return (int(origin_x + fx * cell), int(origin_y + fy * cell))


def test_hover_near_horizontal_edge_previews_horizontal_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    window.view.handle_motion(_pos_for(window, 4.4, 4.0), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall == ("h", 3, 3)
    assert window.view._hover_legal is True


def test_hover_near_vertical_edge_previews_vertical_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    window.view.handle_motion(_pos_for(window, 4.0, 4.4), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall == ("v", 3, 3)


def test_hover_in_cell_center_shows_pawn_target(make_window):
    window = make_window(mode="pvp")
    session = window.session
    window.view.handle_motion(_pos_for(window, 4.5, 7.5), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall is None
    assert window.view._hover_target == (4, 7)


def test_click_on_edge_places_wall_without_any_mode(make_window):
    """核心交互：不需要切模式，鼠标放到格子边缘直接点击就落墙。"""
    window = make_window(mode="pvp")
    session = window.session
    pos = _pos_for(window, 4.4, 4.0)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.walls_left[0] == 9
    assert session.state.h_mask != 0  # 放的是横墙


def test_click_on_edge_places_vertical_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    pos = _pos_for(window, 4.0, 4.4)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.v_mask != 0  # 放的是竖墙


def test_click_in_cell_center_moves_pawn(make_window):
    """点击格子中心是走子，不会被当成放墙。"""
    window = make_window(mode="pvp")
    session = window.session
    pos = _pos_for(window, 4.5, 7.5)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.pawns[0] == (4, 7)
    assert session.state.walls_left[0] == 10  # 没消耗墙


def test_illegal_wall_position_falls_back_to_pawn_move(make_window):
    """在放不下墙的位置点击时，若底下格子是合法落点就走子，而不是毫无反应。"""
    from boardgames.games.quoridor.state import QuoridorState

    window = make_window(mode="pvp")
    session = window.session
    # 玩家 1 的墙用完了 → 所有墙位都非法
    session.state = QuoridorState(
        size=9,
        pawns=((4, 8), (4, 0)),
        walls_left=(0, 10),
        h_mask=0,
        v_mask=0,
        current=0,
        ply=0,
    )

    pos = _pos_for(window, 4.4, 7.0)  # 位于 (4,7) 的上边缘
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert session.state.pawns[0] == (4, 7), "非法墙位上应当退化为走子"
    assert session.state.walls_left[0] == 0


def test_undo_returns_to_opening(make_window):
    window = make_window(mode="pvp")
    session = window.session
    target = session.game.pawn_moves_for(session.state, 0)[0].dst
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": window.view.cell_center(*target), "button": 1})
    )
    window._handle_events()
    assert len(session.history) == 2

    window._on_action("undo", None)
    assert len(session.history) == 1
    assert session.state.pawns[0] == (4, 8)


def test_human_vs_ai_ai_replies(make_window):
    window = make_window(
        mode="pve", p1_type="human", p2_type="minimax",
        minimax_depth=2, minimax_time_ms=200, ai_delay_ms=0, anim_ms=0,
    )
    session = window.session
    target = session.game.pawn_moves_for(session.state, 0)[0].dst
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": window.view.cell_center(*target), "button": 1})
    )
    window._handle_events()
    assert session.state.current_player == 1

    # AI 的时限用真实时钟，所以这里必须按真实时间等待
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        window._update(16.0)
        if session.state.current_player == 0 or session.is_over:
            break
        time.sleep(0.003)
    assert session.state.current_player == 0 or session.is_over
    assert len(session.history) == 3


def test_ai_self_play_makes_progress(make_window):
    window = make_window(
        mode="eve", p1_type="minimax", p2_type="minimax",
        minimax_depth=1, minimax_time_ms=120, ai_delay_ms=0, anim_ms=0,
    )
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        window._update(16.0)
        if window.session.is_over or len(window.session.history) > 5:
            break
        time.sleep(0.003)
    assert len(window.session.history) > 2, "AI 自对弈没有推进"


def test_changing_board_size_restarts(make_window):
    window = make_window(mode="pvp", board_size=9)
    window._on_setting("board_size", 7)
    assert window.session.state.size == 7
    assert window.session.state.pawns == ((3, 6), (3, 0))
    assert len(window.session.history) == 1


def test_sidebar_keeps_only_relevant_groups(make_window):
    """精简 UI：双人对战不显示 AI 相关分组。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    active = {s.group_id for s in window.sidebar._active_sections()}
    assert active == {"game", "ui"}
    assert not window.sidebar._show_thinking_row()


def test_sidebar_shows_minimax_only_when_used(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window._update(16.0)
    active = {s.group_id for s in window.sidebar._active_sections()}
    assert "minimax" in active
    assert "mcts" not in active
    assert "players" in active
    assert "eval" in active
    assert window.sidebar._show_thinking_row()


def test_sidebar_shows_mcts_only_when_used(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="mcts")
    window._update(16.0)
    active = {s.group_id for s in window.sidebar._active_sections()}
    assert "mcts" in active
    assert "minimax" not in active


def test_sidebar_hides_engine_groups_for_random(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="random")
    window._update(16.0)
    active = {s.group_id for s in window.sidebar._active_sections()}
    assert "minimax" not in active and "mcts" not in active and "eval" not in active


def test_sidebar_switching_mode_updates_groups(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    assert "minimax" not in {s.group_id for s in window.sidebar._active_sections()}

    window._on_setting("mode", "pve")
    window._on_setting("p2_type", "minimax")
    window._update(16.0)
    assert "minimax" in {s.group_id for s in window.sidebar._active_sections()}


def test_settings_are_persisted(make_window):
    window = make_window(mode="pvp")
    window._on_setting("minimax_depth", 5)
    window._flush_settings()
    reloaded = Settings.load(window.settings.path)
    assert reloaded.get("minimax_depth") == 5
