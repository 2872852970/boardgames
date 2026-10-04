"""对局界面这一轮的交互约定：公共选项锁定、二级确认、结算可关、设置浮层。

这些行为都是"界面上的规矩"，规则测试与 AI 测试都照不到，只能在这里守：

* 棋局设置（棋盘尺寸 / 起始布局 / 扩展虫 / 先手）是**全局公共选项**，
  开始对弈后必须锁死，只有开新局才能再改；
* 「新局」「大厅」在**已经落过子**时要先弹二级确认；
* 结算浮层会盖住棋盘，得能关掉；
* 「设置」浮层收着评估权重与界面参数，并且是模态的。
"""

from __future__ import annotations

import pygame
import pytest
from helpers import find_widget, key_event, press, release

from boardgames.app import build_registry
from boardgames.settings import Settings
from boardgames.ui.window import GameWindow


def _play_one_move(window) -> None:
    """让玩家 1 走一步（直接在棋盘上点目标格）。"""
    move = window.session.game.pawn_moves_for(window.session.state, 0)[0]
    pos = window.view.cell_center(*move.dst)
    pygame.event.post(press(pos))
    window._handle_events()


def _click(window, pos) -> None:
    pygame.event.post(press(pos))
    pygame.event.post(release(pos))
    window._handle_events()


# --------------------------------------------------------------------------- #
# 棋局设置：公共选项、排最上面、开局后锁定
# --------------------------------------------------------------------------- #

def test_board_settings_sit_at_the_top_of_the_sidebar(make_window):
    """棋局设置是公共选项，必须排在 AI 状态行与其它分组前面。"""
    window = make_window(mode="eve")
    window._update(16.0)
    flow = [gid for _, gid in window.sidebar._flow()]
    assert flow[0] == "game", f"棋局设置没排第一：{flow}"


def test_board_settings_are_editable_on_a_fresh_board(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    widget = find_widget(window.sidebar, "board_size")
    assert widget.enabled, "空棋盘上应该能调棋盘尺寸"


def test_board_settings_lock_once_the_game_starts(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    window._update(16.0)

    for key in ("board_size", "walls_per_player"):
        widget = find_widget(window.sidebar, key)
        assert not widget.enabled, f"开局后 {key} 还是可改的"

    # 锁死之后点它不该有任何效果（事件也进不去）
    widget = find_widget(window.sidebar, "board_size")
    before = window.settings.get("board_size")
    _click(window, widget.rect.center)
    assert window.settings.get("board_size") == before


def test_board_settings_unlock_after_undo_back_to_the_start(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    window._update(16.0)
    assert not find_widget(window.sidebar, "board_size").enabled

    window._on_action("undo", None)
    window._update(16.0)
    assert find_widget(window.sidebar, "board_size").enabled, "退回到开局就该解锁"


# --------------------------------------------------------------------------- #
# 二级确认
# --------------------------------------------------------------------------- #

def test_new_game_asks_for_confirmation_mid_game(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    window._on_action("new_game", None)

    assert window.match._confirm.open, "开局后点「新局」该先问一句"
    assert len(window.session.history) > 1, "确认之前不能真的重开"


def test_confirming_starts_a_new_game(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    window._on_action("new_game", None)
    window.match._confirm.buttons[0].on_click()

    assert not window.match._confirm.open
    assert len(window.session.history) == 1, "确认后应当回到开局"


def test_cancelling_keeps_the_game(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    before = len(window.session.history)
    window._on_action("new_game", None)
    window.match._confirm.buttons[1].on_click()
    assert len(window.session.history) == before


def test_fresh_board_does_not_ask(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    window._on_action("new_game", None)
    assert not window.match._confirm.open, "空棋盘没必要二次确认"


def test_lobby_button_asks_for_confirmation_mid_game(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    window._on_action("lobby", None)

    assert window.match._confirm.open
    assert window.scene is window.match, "确认之前不该离开对局"

    window.match._confirm.buttons[0].on_click()
    assert window.scene is window.lobby


def test_confirmation_is_modal(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    _play_one_move(window)
    before = len(window.session.history)
    window._on_action("new_game", None)

    # 浮层开着时点棋盘不该落子
    move = window.session.game.pawn_moves_for(window.session.state, window.session.state.current_player)
    _click(window, window.view.cell_center(*move[0].dst))
    assert len(window.session.history) == before

    # Esc 关掉它
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert not window.match._confirm.open


# --------------------------------------------------------------------------- #
# 结算浮层：可以关掉，露出棋盘
# --------------------------------------------------------------------------- #

def _finished(window) -> None:
    window._update(16.0)
    window.session.resign()
    window._update(16.0)


def test_result_overlay_has_a_close_button(make_window):
    window = make_window(mode="pvp")
    _finished(window)
    close = window.match._result_close
    assert window.match.board_area.colliderect(close.rect), "× 该画在棋盘区里"


def test_result_overlay_can_be_dismissed_to_see_the_board(make_window):
    window = make_window(mode="pvp")
    _finished(window)
    assert not window.match._result_dismissed

    window.match._dismiss_result()
    window._update(16.0)
    assert window.match._result_dismissed
    assert all(not b.visible for b in window.match._overlay_buttons), "关掉后按钮也该收起来"


def test_a_new_game_brings_the_result_overlay_back(make_window):
    window = make_window(mode="pvp")
    _finished(window)
    window.match._dismiss_result()
    window._restart()
    assert not window.match._result_dismissed


def test_restarting_clears_the_finished_state(make_window):
    window = make_window(mode="pvp")
    _finished(window)
    assert window.session.is_over
    window._restart()
    window._update(16.0)
    assert not window.session.is_over, "重开之后不该还停在结算态"


# --------------------------------------------------------------------------- #
# 设置浮层
# --------------------------------------------------------------------------- #

def test_footer_has_settings_and_no_resign(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    labels = [b.label for b in window.sidebar._visible_footer()]
    assert "设置" in labels
    assert "认输" not in labels, "认输按钮没有意义，已经删掉"


def test_settings_button_opens_the_panel(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    button = next(b for b in window.sidebar.footer_buttons if b.key == "settings")
    button.on_click()
    assert window.settings_panel.open


def test_settings_panel_holds_the_less_used_params(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    keys = {w.key for w in window.settings_panel._visible_widgets()}
    assert "show_hints" in keys and "anim_ms" in keys
    assert "w_path" in keys, "评估权重也在设置里"
    assert "board_size" not in keys, "常用项不该跑到设置浮层来"


def test_settings_panel_groups_can_be_collapsed(make_window):
    """点分组标题把整组收起 / 展开（与侧栏一致）。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    panel = window.settings_panel
    panel.show("quoridor", window.session.resolved_player_types())
    window._update(16.0)

    eval_group = panel.group("eval")
    assert eval_group.expanded, "默认展开：点开就是为了改它们"
    assert "w_path" in {w.key for w in panel._visible_widgets()}

    header = next(rect for group, rect in panel._headers if group is eval_group)
    pygame.event.post(press(header.center))
    window._handle_events()
    assert not eval_group.expanded, "点标题行应当收起"
    keys = {w.key for w in panel._visible_widgets()}
    assert "w_path" not in keys, "收起后不该还能接到（也不该画出来）"
    assert "anim_ms" in keys, "另一组不受影响"

    # 再点一次展开回来
    header = next(rect for group, rect in panel._headers if group is eval_group)
    pygame.event.post(press(header.center))
    window._handle_events()
    assert eval_group.expanded
    assert "w_path" in {w.key for w in panel._visible_widgets()}


def test_collapsed_settings_group_keeps_no_live_widgets(make_window):
    """收起的分组：控件既不可见，也不该留在能接事件的坐标上。"""
    window = make_window(mode="pvp")
    window._update(16.0)
    panel = window.settings_panel
    panel.show("quoridor", window.session.resolved_player_types())

    ui_group = panel.group("ui")
    ui_group.expanded = False
    panel._layout_content()
    hidden = [w for w in ui_group.widgets if panel._widget_applicable(w)]
    assert hidden, "「界面与操作」这组总得有东西"
    assert all(not w.visible for w in hidden)
    assert all(w.rect.bottom < 0 for w in hidden), "收起的控件必须挪出画面，否则会被点到"


def test_settings_panel_is_modal_and_closes_on_escape(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    before = len(window.session.history)
    _play_one_move(window)
    assert len(window.session.history) == before, "浮层开着时棋盘不该响应"

    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert not window.settings_panel.open


def test_settings_panel_clicking_the_veil_closes_it(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    _click(window, (4, 4))
    assert not window.settings_panel.open


# --------------------------------------------------------------------------- #
# 新游戏的初始模式
# --------------------------------------------------------------------------- #

@pytest.fixture
def lobby_window(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    settings.values["mode"] = "eve"  # 上一次留下的选择
    window = GameWindow(settings, build_registry(), offscreen=True, start_scene="lobby")
    yield window
    if pygame.get_init():
        pygame.quit()


def test_a_new_game_starts_in_two_player_mode(lobby_window):
    window = lobby_window
    assert str(window.settings.get("mode")) == "eve"
    window.goto_match("connect4")
    assert str(window.settings.get("mode")) == "pvp", "每个新游戏的初始状态都是双人对战"
    assert window.settings_panel is not None


# --------------------------------------------------------------------------- #
# 设置浮层里的数值框
# --------------------------------------------------------------------------- #

def _panel_slider(window, key):
    window._update(16.0)
    for _ in range(40):
        widget = next(
            (w for w in window.settings_panel._visible_widgets() if w.key == key), None
        )
        if widget is not None and window.settings_panel._content_clip().contains(widget.rect):
            return widget
        window.settings_panel.scroll = min(
            window.settings_panel.max_scroll, window.settings_panel.scroll + 60
        )
        window.settings_panel._layout_content()
    raise AssertionError(f"设置浮层里找不到完全可见的 {key}")


def _post_key(window, key: int, unicode: str = "") -> None:
    pygame.event.post(key_event(key, unicode))
    window._handle_events()


def _clear_input(window, count: int = 12) -> None:
    for _ in range(count):
        _post_key(window, pygame.K_BACKSPACE)


def _type(window, text: str) -> None:
    for char in text:
        code = getattr(pygame, f"K_{char}", 0) if char.isalnum() else 0
        _post_key(window, code, char)


def test_settings_panel_value_box_accepts_typed_input(make_window):
    """设置浮层里的数值框也能点进去直接键入（键盘先给输入框，不关浮层）。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    slider = _panel_slider(window, "minimax_depth")

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    assert slider.editing, "点数值框该进入输入态"

    _clear_input(window)
    _type(window, "7")
    _post_key(window, pygame.K_RETURN)

    assert not slider.editing
    assert slider.value == 7
    assert window.settings.get("minimax_depth") == 7
    assert window.settings_panel.open, "回车确认不该把浮层关掉"


def test_escape_while_editing_only_cancels_the_input(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    slider = _panel_slider(window, "minimax_depth")
    before = slider.value

    pygame.event.post(press(slider.value_box.center))
    window._handle_events()
    _clear_input(window)
    _type(window, "9")
    _post_key(window, pygame.K_ESCAPE)

    assert not slider.editing
    assert slider.value == before, "Esc 只应该取消这次输入"
    assert window.settings_panel.open, "Esc 先还给输入框，不该直接关浮层"


# --------------------------------------------------------------------------- #
# 设置浮层：尺寸恒定 + 每一项都能恢复初始值
# --------------------------------------------------------------------------- #

def _open_panel(window, **overrides):
    for key, value in overrides.items():
        window.settings.values[key] = value
    window.settings_panel.show("quoridor", window.session.resolved_player_types())
    window._update(16.0)
    return window.settings_panel


def test_settings_panel_size_is_stable_when_groups_collapse(make_window):
    """折叠 / 展开分组只该改变滚动内容，卡片尺寸与关闭按钮一帧都不动。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    panel = _open_panel(window)
    card = panel._card.copy()
    close = panel._close_button.rect.copy()

    for group in panel._groups:
        group.expanded = False
    panel._layout_content()
    assert panel._card == card, "折叠分组不该改变卡片尺寸"
    assert panel._close_button.rect == close

    for group in panel._groups:
        group.expanded = True
    panel._layout_content()
    assert panel._card == card, "展开也不该改变卡片尺寸"
    assert panel._close_button.rect == close


def test_every_visible_row_offers_a_reset_button(make_window):
    """每个显示出来的参数都带 ↺；改过的亮、没改过的暗。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    panel = _open_panel(window)
    widgets = [w for w in panel._visible_widgets() if hasattr(w, "supports_reset")]
    assert widgets, "浮层里总该有能恢复初始值的项"
    assert all(w.supports_reset for w in widgets), "可见的每一项都该支持恢复初始值"

    slider = next(w for w in widgets if w.key == "minimax_depth")
    assert not slider.has_reset, "没改过时 ↺ 应是暗的（不可点）"
    assert slider.default == 4

    window.settings.values["minimax_depth"] = 7
    slider.set_value_silently(7)
    assert slider.has_reset

    pygame.event.post(press(slider.reset_rect.center))
    window._handle_events()
    assert window.settings.get("minimax_depth") == 4, "点 ↺ 该恢复默认值"
    assert not slider.has_reset, "恢复之后 ↺ 该重新变暗"


def test_reset_all_restores_only_the_visible_items(make_window):
    """「全部恢复默认」只动这一局用得上的项，别把别的棋类的调参一起刷掉。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    panel = _open_panel(window, minimax_depth=7, minimax_time_ms=9999, show_hints=False,
                        w_material=42.0)  # w_material 是四子棋的，墙棋这里不显示
    assert panel._reset_all.enabled, "有改过的项时按钮该可点"

    _click(window, panel._reset_all.rect.center)
    assert window.settings.get("minimax_depth") == 4
    assert window.settings.get("minimax_time_ms") == 1200
    assert window.settings.get("show_hints") is True
    assert window.settings.get("w_material") == 42.0, "别的棋类的参数不该被一起重置"
    assert not panel._reset_all.enabled, "全部恢复默认后按钮该变灰"


def test_hint_chip_reports_the_blocking_reason_when_it_is_not_my_turn(make_window):
    """AI 回合的左上角胶囊不该还在教「该你走的操作」，而要说明现在为什么轮不到你。"""
    window = make_window(
        mode="pve", p1_type="human", p2_type="mcts",
        mcts_iterations=60, mcts_time_ms=120, ai_delay_ms=0, anim_ms=0,
    )
    window._update(16.0)
    session = window.session
    move = session.game.pawn_moves_for(session.state, 0)[0]
    pygame.event.post(press(window.view.cell_center(*move.dst)))
    window._handle_events()
    window._update(16.0)

    assert session.state.current_player == 1
    assert not window.match._interactive()
    label = window.match._idle_label(False)
    assert label and label == window.match._blocked_reason()
    assert "AI" in label, "胶囊该直说「AI 正在思考」，而不是教玩家怎么走"
