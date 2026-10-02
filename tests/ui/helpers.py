"""UI 测试里模拟鼠标 / 键盘的小工具。"""

from __future__ import annotations

import pygame


def pos_for(window, fx: float, fy: float) -> tuple[int, int]:
    """把"格坐标"（可以是小数）换算成棋盘上的像素坐标。"""
    origin_x, origin_y = window.view.origin
    cell = window.view.cell
    return (int(origin_x + fx * cell), int(origin_y + fy * cell))


def find_widget(sidebar, key: str):
    for section in sidebar.sections:
        for widget in section.widgets:
            if widget.key == key:
                return widget
    return None


def visible_slider(window, key: str):
    """滚动到该滑块**完整**可见为止（事件只在可见区域内派发）。"""
    sidebar = window.sidebar
    for _ in range(40):
        window._update(16.0)
        widget = find_widget(sidebar, key)
        if widget is not None and widget.visible and sidebar.viewport.contains(widget.rect):
            return widget
        sidebar._scroll_by(60)
    raise AssertionError(f"找不到完整可见的滑块: {key}")


def motion(pos) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (0, 0, 0)})


def press(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": button})


def release(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": button})


def key_event(key: int, unicode: str = "") -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, {"key": key, "unicode": unicode, "mod": 0})


def type_text(window, text: str) -> None:
    """逐字符输入到当前获得焦点的数值框。"""
    for char in text:
        code = getattr(pygame, f"K_{char}", 0) if char.isalnum() else 0
        window.sidebar.handle_key(key_event(code, char))


def clear_input(window, length: int = 12) -> None:
    for _ in range(length):
        window.sidebar.handle_key(key_event(pygame.K_BACKSPACE))
