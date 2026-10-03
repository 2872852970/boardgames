"""规则说明浮层：对局里的入口、模态性、滚动与容错。

大厅那边的入口在 ``test_lobby.py``（卡片按钮 / R 键），这里只管对局场景与
浮层本身的行为。
"""

from __future__ import annotations

import pygame
from helpers import key_event, press, release

from boardgames.core.game import Game
from boardgames.ui.fonts import FontBook
from boardgames.ui.rules_panel import RulesOverlay, rules_sections


def window_fonts() -> FontBook:
    return FontBook()


def _match_window(make_window, **overrides):
    window = make_window(mode="pvp", **overrides)
    window._update(16.0)
    return window


# --------------------------------------------------------------------------- #
# 对局里的入口
# --------------------------------------------------------------------------- #

def test_match_scene_shows_a_rules_button(make_window):
    window = _match_window(make_window)
    button = window.match._rules_button
    assert button.visible
    assert window.match.board_area.contains(button.rect), "规则按钮该在棋盘区里"
    assert button.rect.right <= window.match.board_area.right


def test_clicking_the_rules_button_does_not_play_a_move(make_window):
    window = _match_window(make_window)
    before = len(window.session.history)
    rect = window.match._rules_button.rect
    pygame.event.post(press(rect.center))
    pygame.event.post(release(rect.center))
    window._handle_events()

    assert window.match.rules.open
    assert len(window.session.history) == before, "点「规则说明」不该顺手走一步棋"


def test_rules_panel_covers_the_sidewall_and_board_while_open(make_window):
    window = _match_window(make_window)
    window.match._open_rules()
    before = len(window.session.history)

    # 点棋盘正中央 —— 浮层开着时这一下必须被吃掉
    pygame.event.post(press(window.match.board_area.center))
    pygame.event.post(release(window.match.board_area.center))
    window._handle_events()
    assert len(window.session.history) == before
    assert window.match.rules.open, "点遮罩会关掉浮层，点卡片里的正文不该关"


def test_h_key_opens_the_rules_in_match(make_window):
    window = _match_window(make_window)
    pygame.event.post(key_event(pygame.K_h))
    window._handle_events()
    assert window.match.rules.open
    assert window.match.rules.game.key == window.game_key


def test_leaving_match_closes_the_rules(make_window):
    window = _match_window(make_window)
    window.match._open_rules()
    window.goto_lobby()
    assert not window.match.rules.open
    assert not window.lobby.rules.open


def test_rules_button_is_in_the_top_right_of_the_board(make_window):
    """按钮的四个角都不该压住左上角那条悬停提示胶囊。"""
    window = _match_window(make_window)
    area = window.match.board_area
    rect = window.match._rules_button.rect
    assert rect.y == area.y + 14
    assert rect.right == area.right - 18


# --------------------------------------------------------------------------- #
# 浮层本身
# --------------------------------------------------------------------------- #

def test_overlay_scrolls_when_the_text_is_long(make_window):
    window = _match_window(make_window, game_key="hive")
    window.match._open_rules()
    overlay = window.match.rules
    assert overlay.max_scroll > 0, "昆虫棋的规则很长，应该要能滚"

    overlay._scroll_by(60)
    assert overlay.scroll > 0
    overlay._scroll_by(-10000)
    assert overlay.scroll == 0.0, "滚动量必须夹在合法范围内"
    overlay._scroll_by(100000)
    assert overlay.scroll == overlay.max_scroll


def test_overlay_keeps_the_close_button_inside_the_card(make_window):
    window = _match_window(make_window)
    window.match._open_rules()
    overlay = window.match.rules
    assert overlay._card.contains(overlay._close.rect)


def test_overlay_fits_every_reasonable_window_size(make_window):
    for size in ((760, 560), (900, 640), (1180, 780), (1600, 900)):
        window = _match_window(make_window)
        window.screen = pygame.display.set_mode(size)
        window._layout()
        window.match._open_rules()
        overlay = window.match.rules
        assert window.screen.get_rect().contains(overlay._card), f"{size} 下规则卡片越界"
        assert overlay._card.width >= 320
        overlay.draw(window.screen, window.fonts)


def test_sections_cover_the_whole_rulebook(make_window):
    window = _match_window(make_window)
    game = window.session.game
    titles = [title for title, _ in rules_sections(game)]
    assert titles[:2] == ["目标", "简介"]
    assert "规则" in titles


def test_sections_fall_back_for_a_game_without_metadata():
    """还没写元数据的棋类也不能画出一个空面板。"""

    class _Bare:
        key = "bare"

    sections = rules_sections(_Bare())
    assert sections and sections[0][1], "空白棋类至少要给一句话"

    overlay = RulesOverlay()
    overlay.show(_Bare())
    assert overlay.open
    assert overlay._lines, "兜底文案也要真的排出一行来"
    surface = pygame.Surface((900, 640))
    overlay.layout(surface.get_rect())
    overlay.draw(surface, window_fonts())


def test_game_metadata_hooks_exist_on_the_base_class():
    """``goal`` / ``howto`` / ``tips`` 是给 UI 读的**可选** ClassVar。"""
    assert Game.goal == ""
    assert Game.howto == ()
    assert Game.tips == ()
