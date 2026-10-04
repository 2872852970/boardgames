"""无头 UI 冒烟测试：真正把窗口、交互、AI 串起来跑一遍。

使用 SDL 的 dummy 视频驱动，因此不需要真实显示器。
"""

from __future__ import annotations

import time

import pygame
from helpers import key_event as _key  # noqa: F401  (供后续用例使用)
from helpers import motion as _motion  # noqa: F401
from helpers import pos_for as _pos_for
from helpers import press

from boardgames.games.quoridor.view import WALL_MODE_KEY
from boardgames.settings import PLAYER_TYPE_LABELS, Settings


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


def _wall_mode(window, on: bool = True) -> None:
    window.view_state.extra[WALL_MODE_KEY] = on


def test_wall_mode_previews_horizontal_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    _wall_mode(window)
    window.view.handle_motion(_pos_for(window, 4.4, 4.0), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall == ("h", 3, 3)
    assert window.view._hover_legal is True


def test_wall_mode_previews_vertical_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    _wall_mode(window)
    window.view.handle_motion(_pos_for(window, 4.0, 4.4), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall == ("v", 3, 3)


def test_no_wall_hint_when_mode_is_off(make_window):
    """不放墙时贴边也不提示，只提示走子落点。"""
    window = make_window(mode="pvp")
    session = window.session
    for fx, fy in ((4.4, 4.0), (4.0, 4.4), (4.0, 4.0)):
        window.view.handle_motion(_pos_for(window, fx, fy), session.game, session.state,
                                  window.view_state)
        assert window.view._hover_wall is None


def test_hover_in_cell_center_shows_pawn_target(make_window):
    window = make_window(mode="pvp")
    session = window.session
    window.view.handle_motion(_pos_for(window, 4.5, 7.5), session.game, session.state,
                              window.view_state)
    assert window.view._hover_wall is None
    assert window.view._hover_target == (4, 7)


def test_wall_mode_click_places_horizontal_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    _wall_mode(window)
    pos = _pos_for(window, 4.4, 4.0)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.walls_left[0] == 9
    assert session.state.h_mask != 0  # 放的是横墙
    # 一回合只放一面墙：放完自动退出放墙模式
    assert window.view_state.extra[WALL_MODE_KEY] is False


def test_wall_mode_click_places_vertical_wall(make_window):
    window = make_window(mode="pvp")
    session = window.session
    _wall_mode(window)
    pos = _pos_for(window, 4.0, 4.4)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.v_mask != 0  # 放的是竖墙


def test_click_in_cell_center_moves_pawn(make_window):
    """不在放墙模式时，点击落点就是走子。"""
    window = make_window(mode="pvp")
    session = window.session
    pos = _pos_for(window, 4.5, 7.5)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 2
    assert session.state.pawns[0] == (4, 7)
    assert session.state.walls_left[0] == 10  # 没消耗墙


def test_wall_mode_click_on_illegal_spot_does_nothing(make_window):
    """放墙模式下点到放不了的位置：不放墙，也不顺手走子。"""
    from boardgames.games.quoridor.state import QuoridorState

    window = make_window(mode="pvp")
    session = window.session
    session.state = QuoridorState(
        size=9, pawns=((4, 8), (4, 0)), walls_left=(0, 10),
        h_mask=0, v_mask=0, current=0, ply=0,
    )
    _wall_mode(window)
    pos = _pos_for(window, 4.4, 4.0)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    window._handle_events()

    assert len(session.history) == 1, "非法墙位不该产生着法"
    assert session.state.pawns[0] == (4, 8)


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
    session = window.session
    assert session.paused is True, "AI 自对弈应当默认暂停"
    session.paused = False  # 本用例要验证"自动连续对弈"这条路

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
    """精简 UI：双人对战不显示 AI 相关分组，引擎参数一律不在侧栏。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    active = {s.group_id for s in window.sidebar._active_sections()}
    # 「引擎参数 / 评估权重 / 界面与操作」都收进「设置」浮层，侧栏只留常用分组
    assert active == {"game"}
    assert not window.sidebar._show_thinking_row()


def test_engine_params_live_in_the_settings_panel(make_window):
    """引擎参数从侧栏搬进了「设置」浮层 —— 侧栏里一个都不该剩。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window._update(16.0)
    assert "minimax" not in {s.group_id for s in window.sidebar.sections}
    assert "mcts" not in {s.group_id for s in window.sidebar.sections}
    assert {s.group_id for s in window.sidebar._active_sections()} == {"game", "players"}
    assert window.sidebar._show_thinking_row()


def test_settings_panel_shows_only_the_engine_in_play(make_window):
    """设置里只列**实际参战**的引擎参数：Minimax 局里不该冒出 MCTS 的旋钮。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    keys = {w.key for w in window.settings_panel._visible_widgets()}
    assert "minimax_depth" in keys and "minimax_time_ms" in keys
    assert "mcts_iterations" not in keys

    other = make_window(mode="pve", p1_type="human", p2_type="mcts")
    other._update(16.0)
    other.settings_panel.show("quoridor", other.session.resolved_player_types())
    keys = {w.key for w in other.settings_panel._visible_widgets()}
    assert "mcts_iterations" in keys
    assert "minimax_depth" not in keys


def test_settings_panel_hides_engine_params_for_pvp(make_window):
    """双人对战没有任何引擎参战：设置里只剩评估权重与界面参数。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    keys = {w.key for w in window.settings_panel._visible_widgets()}
    assert "minimax_depth" not in keys and "mcts_iterations" not in keys
    assert "show_hints" in keys and "w_path" in keys


def test_settings_panel_follows_the_engine_when_mode_changes(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    window._on_setting("mode", "pve")
    window._on_setting("p2_type", "minimax")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    assert "minimax_depth" in {w.key for w in window.settings_panel._visible_widgets()}


def test_settings_panel_shows_no_engine_for_random(make_window):
    """随机走子没有可调参数，设置里也不该出现任何引擎分组。"""
    window = make_window(mode="pve", p1_type="human", p2_type="random")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    keys = {w.key for w in window.settings_panel._visible_widgets()}
    assert "minimax_depth" not in keys and "mcts_iterations" not in keys
    assert "w_path" in keys, "评估权重与引擎无关，照常显示"


def test_pve_dropdowns_match_the_saved_settings_at_startup(make_window):
    """回归：开局时"电脑 AI"下拉必须显示**真正会跑**的那个引擎。

    两个虚拟控件（我执 / 电脑 AI）是按默认值造出来的，必须立刻从 settings
    反推一次；不反推的话配置里存着 MCTS，界面却写着 Minimax。
    """
    window = make_window(mode="pve", p1_type="mcts", p2_type="human")
    window._update(16.0)
    assert window.sidebar._pve_side.value == "p2"
    assert window.sidebar._pve_ai.value == "mcts"
    assert window.session.resolved_player_types() == ("mcts", "human")
    assert window.sidebar._pve_ai.display() == PLAYER_TYPE_LABELS["mcts"]


def test_pve_settings_are_normalized_to_match_what_runs(make_window):
    """配置里"两边都是 AI"时，真正跑的是"玩家 1 人类 + 玩家 2 的引擎"。

    这个组合必须**归一化**写回设置，否则 JSON 里躺着一份、界面显示另一份、
    实际又跑第三份 —— 这正是"下拉菜单和实际运行的 AI 不符"的来源。
    """
    window = make_window(mode="pve", p1_type="mcts", p2_type="minimax")
    window._update(16.0)
    assert window.session.resolved_player_types() == ("human", "minimax")
    assert window.settings.get("p1_type") == "human"
    assert window.settings.get("p2_type") == "minimax"
    assert window.sidebar._pve_side.value == "p1"
    assert window.sidebar._pve_ai.value == "minimax"


def test_footer_is_two_rows_and_keeps_the_same_actions(make_window):
    window = make_window(mode="eve", p1_type="minimax", p2_type="minimax")
    window._update(16.0)
    rows = window.sidebar._footer_rows
    assert len(rows) == 2, "底栏分两行，窄侧栏下按钮才不会挤成一团"
    keys = [key for row in rows for key in row]
    assert keys == ["new_game", "undo", "pause", "step", "lobby", "settings"]
    rects = [b.rect for b in window.sidebar.footer_buttons]
    assert all(r.width > 0 for r in rects), "底栏按钮必须已经排好位置"
    assert max(r.bottom for r in rects) <= window.sidebar.rect.bottom


def test_settings_are_persisted(make_window):
    window = make_window(mode="pvp")
    window._on_setting("minimax_depth", 5)
    window._flush_settings()
    reloaded = Settings.load(window.settings.path)
    assert reloaded.get("minimax_depth") == 5


# --------------------------------------------------------------------------- #
# 先手已固定为玩家 1（设置里的「先手」下拉去掉了）
# --------------------------------------------------------------------------- #

def test_first_player_is_fixed_to_player_one(make_window):
    from boardgames.settings.schema import SPEC_BY_KEY

    assert "first_player" not in SPEC_BY_KEY, "「先手」参数应已从设置里移除"
    window = make_window(mode="pvp")
    assert window.session.state.current_player == 0
    # 换棋盘（会重开一局）之后仍然由玩家 1 先手
    window._on_setting("board_size", 7)
    assert window.session.state.current_player == 0


# --------------------------------------------------------------------------- #
# 三种模式只在开局前可选
# --------------------------------------------------------------------------- #

def test_mode_is_selectable_only_before_the_game_starts(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    mode_widget = window.sidebar._mode_widget
    assert mode_widget.enabled, "空棋盘上应该能切模式"

    target = mode_widget._cell(1).center  # 第 2 格 = 人机对战
    pygame.event.post(press(target))
    window._handle_events()
    assert str(window.settings.get("mode")) == "pve", "开局前点模式该生效"

    # 走一步 → 模式锁定
    window._on_setting("mode", "pvp")
    window._update(16.0)
    session = window.session
    move = session.game.pawn_moves_for(session.state, 0)[0]
    pygame.event.post(press(window.view.cell_center(*move.dst)))
    window._handle_events()
    window._update(16.0)

    assert not window.sidebar._mode_widget.enabled, "开局后模式必须锁死"
    before = str(window.settings.get("mode"))
    pygame.event.post(press(window.sidebar._mode_widget._cell(1).center))
    window._handle_events()
    assert str(window.settings.get("mode")) == before, "锁死后点它不该有任何效果"

    window._restart()
    window._update(16.0)
    assert window.sidebar._mode_widget.enabled, "开新局后解锁"


def test_state_changes_never_move_the_fixed_header(make_window):
    """布局稳定性：状态怎么变，固定头部（玩家卡片 / 滚动区）都不许移动。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    players = window.sidebar._players_rect.copy()
    viewport = window.sidebar.viewport.copy()
    mode_rect = window.sidebar._mode_widget.rect.copy()

    session = window.session
    move = session.game.pawn_moves_for(session.state, 0)[0]
    pygame.event.post(press(window.view.cell_center(*move.dst)))
    window._handle_events()
    window._update(16.0)

    assert window.sidebar._players_rect == players
    assert window.sidebar.viewport == viewport
    assert window.sidebar._mode_widget.rect == mode_rect
