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

    for key in ("board_size", "walls_per_player", "first_player"):
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
