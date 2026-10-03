"""无边框窗口 + 自绘标题栏。

"无头"在这个项目里指的是**没有 pygame 那条系统标题栏**（``pygame.NOFRAME``），
窗口照常显示、照常能玩；程序自己画一条补上关闭 / 全屏 / 最小化 / 拖动。
真的"不显示窗口"是另一个开关（``offscreen``，给 CI 与跑批用），这里也守着。
"""

from __future__ import annotations

import pygame
import pytest
from helpers import press, release

from boardgames.app import build_registry
from boardgames.settings import Settings
from boardgames.ui.chrome import BTN_W, MAXIMIZE, MINIMIZE, TITLEBAR_H, TitleBar
from boardgames.ui.window import GameWindow


@pytest.fixture
def make_frameless(tmp_path):
    created: list[GameWindow] = []

    def _make(**kwargs) -> GameWindow:
        settings = Settings(tmp_path / "settings.json")
        for key, value in kwargs.pop("settings_values", {}).items():
            settings.values[key] = value
        window = GameWindow(
            settings, build_registry(), offscreen=True, frameless=True,
            start_scene=kwargs.pop("start_scene", "lobby"), **kwargs,
        )
        created.append(window)
        return window

    yield _make
    for _window in created:
        if pygame.get_init():
            pygame.quit()


# --------------------------------------------------------------------------- #
# 开窗
# --------------------------------------------------------------------------- #

def test_frameless_window_builds_its_own_title_bar(make_frameless):
    window = make_frameless()
    assert window.frameless
    assert window.titlebar is not None
    assert window.titlebar.rect.height == TITLEBAR_H


def test_a_normal_window_has_no_title_bar(make_window):
    window = make_window()
    assert not window.frameless
    assert window.titlebar is None


def test_scenes_get_the_area_below_the_title_bar(make_frameless):
    window = make_frameless()
    content = window.content_rect
    assert content.top == TITLEBAR_H
    assert content.bottom == window.screen.get_rect().bottom
    assert content.height == window.screen.get_rect().height - TITLEBAR_H
    # 大厅的卡片必须整块落在标题栏下面
    for card in window.lobby._cards:
        assert card.rect.top >= TITLEBAR_H


def test_title_bar_follows_the_game_name(make_frameless):
    window = make_frameless()
    assert "选棋" in window.titlebar.title
    window.goto_match("connect4")
    assert "重力四子棋" in window.titlebar.title


def test_match_scene_also_stays_below_the_title_bar(make_frameless):
    """对局场景早先漏了 ``area.y``：侧栏与棋盘从 y=0 开始，被标题栏压掉一条。"""
    window = make_frameless()
    window.goto_match("hive")
    window._update(16.0)
    match = window.match
    assert match.board_area.top == TITLEBAR_H
    assert match.sidebar_rect.top == TITLEBAR_H
    # 侧栏第一行内容（游戏名 / 模式切换）也得整块落在标题栏下面
    assert match.sidebar.viewport.top > TITLEBAR_H
    widget = next(w for w in match.sidebar._visible_widgets() if w.key == "hive_expansion")
    assert widget.rect.top >= TITLEBAR_H, "棋局设置的控件跑到标题栏底下了"


def test_resizing_keeps_the_window_frameless(make_frameless):
    window = make_frameless()
    pygame.event.post(pygame.event.Event(pygame.VIDEORESIZE, {"size": (1000, 660), "w": 1000, "h": 660}))
    window._handle_events()
    assert window.titlebar is not None
    assert window.content_rect.width == window.screen.get_rect().width


# --------------------------------------------------------------------------- #
# 标题栏上的按钮
# --------------------------------------------------------------------------- #

def _click(window, pos) -> None:
    pygame.event.post(press(pos))
    pygame.event.post(release(pos))
    window._handle_events()


def _button(window: GameWindow, kind: str):
    return next(b for b in window.titlebar._buttons if b.kind == kind)


def test_close_button_quits(make_frameless):
    window = make_frameless()
    _click(window, _button(window, "close").rect.center)
    assert window.running is False


def test_minimize_and_maximize_buttons_do_not_crash(make_frameless):
    window = make_frameless()
    _click(window, _button(window, MINIMIZE).rect.center)
    assert window.running is True, "最小化不该把程序退掉"

    before = window.titlebar.fullscreen
    _click(window, _button(window, MAXIMIZE).rect.center)
    assert window.titlebar.fullscreen != before or not pygame.get_init()


def test_title_bar_buttons_sit_at_the_right_edge(make_frameless):
    window = make_frameless()
    bar = window.titlebar.rect
    close = _button(window, "close")
    assert close.rect.right == bar.right - 8
    assert close.rect.width == BTN_W


# --------------------------------------------------------------------------- #
# 事件路由
# --------------------------------------------------------------------------- #

def test_clicks_below_the_title_bar_still_reach_the_scene(make_frameless):
    window = make_frameless()
    card = window.lobby._cards[0]
    assert card.rect.top > TITLEBAR_H
    _click(window, card.rect.center)
    assert window.scene is window.match, "标题栏不该把下面的点击吞掉"


def test_clicks_on_the_title_bar_never_reach_the_scene(make_frameless):
    window = make_frameless()
    before = len(window.match.session.history)
    window.goto_match()
    _click(window, (window.titlebar.rect.centerx, window.titlebar.rect.centery))
    assert len(window.match.session.history) == before


def test_title_bar_only_consumes_its_own_area():
    """直接对 TitleBar 做单元测试，免得依赖窗口。"""
    bar = TitleBar("测试")
    bar.layout(pygame.Rect(0, 0, 1200, 800))
    assert bar.handle_event(press((600, 5))) is True
    assert bar.handle_event(press((600, 300))) is False


def test_title_bar_draw_paints_the_strip(make_frameless):
    window = make_frameless()
    surface = pygame.Surface((1200, 800))
    surface.fill((0, 0, 0))
    window.titlebar.draw(surface, window.fonts)
    assert surface.get_at((600, TITLEBAR_H // 2))[:3] != (0, 0, 0)


# --------------------------------------------------------------------------- #
# 真的"不显示窗口"
# --------------------------------------------------------------------------- #

def test_offscreen_mode_still_runs_the_whole_loop(make_window):
    window = make_window(mode="pvp")
    assert window.offscreen
    window.run(max_frames=3)
