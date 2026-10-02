"""针对已修复问题的回归测试。

覆盖三个真实 bug：

1. 鼠标划过侧栏分组标题就疯狂折叠/展开（连同里面的下拉菜单一起抖动）；
2. AI 结果已返回、落子停顿未过时主循环每帧重开搜索 → "思考中"闪烁且 AI 不落子；
3. 窗口尺寸不裁剪到屏幕 → 小屏/高 DPI 下底部按钮被裁掉。
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from boardgames.app import build_registry  # noqa: E402
from boardgames.settings import Settings  # noqa: E402
from boardgames.ui import theme  # noqa: E402
from boardgames.ui.window import GameWindow, choose_window_size  # noqa: E402


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


# --------------------------------------------------------------------------- #
# 1. 分组标题：只有左键点击才折叠/展开
# --------------------------------------------------------------------------- #

def test_hovering_section_header_does_not_toggle(make_window):
    window = make_window(mode="pvp")
    sidebar = window.sidebar
    window._update(16.0)  # 先跑一帧，确保标题矩形已算好

    gid, header = next(iter(sidebar._header_rects.items()))
    section = sidebar._section(gid)
    before = section.expanded

    for i in range(12):
        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": header.center, "rel": (0, 0), "buttons": (0, 0, 0)}
            )
        )
        window._handle_events()
        # 逐次断言：用偶数次循环的话，"翻转偶数次回到原状"会掩盖 bug
        assert section.expanded is before, f"第 {i + 1} 次鼠标移动就改变了折叠状态"


def test_clicking_section_header_toggles(make_window):
    window = make_window(mode="pvp")
    sidebar = window.sidebar
    window._update(16.0)
    gid, header = next(iter(sidebar._header_rects.items()))
    section = sidebar._section(gid)
    before = section.expanded

    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": header.center, "button": 1}))
    window._handle_events()
    assert section.expanded is not before

    window._update(16.0)
    header = sidebar._header_rects[gid]
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": header.center, "button": 1}))
    window._handle_events()
    assert section.expanded is before


def test_hovering_dropdown_does_not_toggle_open(make_window):
    # 双人对战模式下"对局双方"分组已被精简掉，所以这里用人机模式
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    sidebar = window.sidebar
    window._update(16.0)

    from boardgames.ui.widgets import Dropdown

    dropdowns = [w for w in sidebar._visible_widgets() if isinstance(w, Dropdown)]
    assert dropdowns, "人机模式下侧栏里应当有下拉控件"
    dropdown = dropdowns[0]
    before = dropdown.open

    for i in range(12):
        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": dropdown._box.center, "rel": (0, 0), "buttons": (0, 0, 0)}
            )
        )
        window._handle_events()
        window._update(16.0)
        assert dropdown.open is before, f"第 {i + 1} 次悬停就改变了展开状态"


def test_hovering_player_rows_never_opens_dropdowns(make_window):
    """鼠标扫过侧栏整条区域也不该把任何下拉打开。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    sidebar = window.sidebar
    window._update(16.0)

    from boardgames.ui.widgets import Dropdown

    for y in range(sidebar.viewport.y + 4, sidebar.viewport.bottom, 7):
        pos = (sidebar.rect.centerx, y)
        pygame.event.post(
            pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (0, 0, 0)})
        )
        window._handle_events()
        window._update(16.0)
        opened = [w.key for w in sidebar._visible_widgets() if isinstance(w, Dropdown) and w.open]
        assert not opened, f"悬停到 y={y} 时意外打开了下拉: {opened}"


# --------------------------------------------------------------------------- #
# 2. AI 等待落子期间不得重开搜索
# --------------------------------------------------------------------------- #

def test_ai_does_not_restart_while_waiting_to_play(make_window):
    window = make_window(
        mode="pve",
        p1_type="human",
        p2_type="minimax",
        minimax_depth=1,
        minimax_time_ms=120,
        ai_delay_ms=400,  # 明显长于 AI 的思考时间，制造"结果已到但还没落子"的窗口
        anim_ms=0,
    )
    session = window.session

    starts: list[int] = []
    original_start = session.worker.start

    def spy(*args, **kwargs):
        starts.append(1)
        return original_start(*args, **kwargs)

    session.worker.start = spy

    target = session.game.pawn_moves_for(session.state, 0)[0].dst
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": window.view.cell_center(*target), "button": 1})
    )
    window._handle_events()
    assert session.state.current_player == 1

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        window._update(16.0)
        if session.state.current_player == 0:
            break
        time.sleep(0.005)

    assert session.state.current_player == 0, "AI 始终没有落子"
    assert len(starts) == 1, f"AI 在等待落子期间被重复启动了 {len(starts)} 次"
    assert len(session.history) == 3


def test_is_thinking_stays_true_until_move_lands(make_window):
    window = make_window(
        mode="eve", p1_type="minimax", p2_type="minimax",
        minimax_depth=1, minimax_time_ms=120, ai_delay_ms=400, anim_ms=0,
    )
    session = window.session
    session.start_thinking()
    assert session.is_thinking()

    # 一直观察到落子为止，"思考中"都不该中途变 False
    deadline = time.monotonic() + 5.0
    flipped_off = False
    while time.monotonic() < deadline:
        window._update(16.0)
        if len(session.history) > 1:
            break
        if not session.is_thinking():
            flipped_off = True
        time.sleep(0.005)

    assert len(session.history) > 1, "AI 没有落子"
    assert not flipped_off, "「思考中」在落子前中途变过 False（会导致界面闪烁）"


# --------------------------------------------------------------------------- #
# 3. 窗口尺寸裁剪到屏幕
# --------------------------------------------------------------------------- #

def test_window_size_clamped_to_screen():
    assert choose_window_size((2560, 1440)) == (theme.WINDOW_W, theme.WINDOW_H)
    assert choose_window_size((1920, 1080)) == (theme.WINDOW_W, theme.WINDOW_H)

    for desktop in ((1097, 617), (1366, 768), (800, 600), (1024, 768)):
        width, height = choose_window_size(desktop)
        assert width <= desktop[0], f"{desktop} 下宽度超出屏幕"
        assert height <= desktop[1], f"{desktop} 下高度超出屏幕"
        assert width >= theme.MIN_WINDOW_W or width == desktop[0]


def test_layout_fits_a_small_window(make_window):
    window = make_window(mode="pvp")
    for size in ((820, 600), (1000, 680), (1180, 780)):
        window.screen = pygame.display.set_mode(size)
        window._layout()
        assert window.sidebar_rect.right <= size[0]
        assert window.sidebar_rect.bottom <= size[1]
        assert window.board_area.right <= size[0]
        assert window.sidebar_rect.left > 0 and window.board_area.width > 200


def test_sidebar_narrows_on_small_windows(make_window):
    window = make_window(mode="pvp")
    window.screen = pygame.display.set_mode((820, 600))
    window._layout()
    assert window.sidebar_rect.width < theme.SIDEBAR_W
    assert window.sidebar_rect.width >= theme.SIDEBAR_MIN_W
    assert window.board_area.width >= 360


# --------------------------------------------------------------------------- #
# 4. 滑块只有按住左键拖动时才跟随鼠标
# --------------------------------------------------------------------------- #

def _find_widget(sidebar, key):
    for section in sidebar.sections:
        for widget in section.widgets:
            if widget.key == key:
                return widget
    return None


def _visible_slider(window, key: str):
    """滚动到该滑块可见为止（事件只在可见区域内派发）。"""
    sidebar = window.sidebar
    for _ in range(40):
        window._update(16.0)
        widget = _find_widget(sidebar, key)
        if widget is not None and widget.visible and sidebar.viewport.colliderect(widget.rect):
            return widget
        sidebar._scroll_by(60)
    raise AssertionError(f"找不到可见的滑块: {key}")


def _motion(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (0, 0, 0)})


def _press(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": button})


def _release(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": button})


def test_slider_does_not_follow_hover(make_window):
    """回归：不按键时鼠标划过滑块，数值不能变。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")
    before = slider.value

    for x in range(slider.rect.x + 4, slider.rect.right - 2, 12):
        for y in (slider.rect.y + 8, slider.rect.y + 34):
            pygame.event.post(_motion((x, y)))
            window._handle_events()
            window._update(16.0)
            assert slider.value == before, "未按下左键时滑块跟随了鼠标"


def test_slider_drag_updates_value(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")
    before = slider.value

    pygame.event.post(_press((slider.rect.x + 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(_motion((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(_release((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()

    assert slider.value > before
    assert slider.value == slider.maximum


def test_slider_drag_ends_when_released_outside_sidebar(make_window):
    """回归：在侧栏外松开左键后，滑块不能再跟着鼠标动。"""
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    slider = _visible_slider(window, "minimax_depth")

    pygame.event.post(_press((slider.rect.x + 4, slider.rect.y + 34)))
    window._handle_events()
    pygame.event.post(_motion((slider.rect.right - 4, slider.rect.y + 34)))
    window._handle_events()
    value_after_drag = slider.value

    # 在棋盘区（侧栏之外）松手
    outside = (10, 10)
    pygame.event.post(_motion(outside))
    window._handle_events()
    pygame.event.post(_release(outside))
    window._handle_events()

    for x in range(slider.rect.x + 4, slider.rect.right - 2, 16):
        pygame.event.post(_motion((x, slider.rect.y + 34)))
        window._handle_events()
        window._update(16.0)
    assert slider.value == value_after_drag, "侧栏外松手后滑块仍然跟随鼠标"
