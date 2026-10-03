"""无边框窗口的自绘标题栏（window chrome）。

为什么要有这个文件
------------------
``pygame.NOFRAME`` 开出来的窗口**没有系统标题栏**，于是：

* 没有关闭按钮 —— 只能 Alt+F4 或摸到 Esc；
* 没法拖动 —— 窗口永远停在初始位置；
* 没有最小化 / 最大化。

所以程序自己画一条：左边是标题，右边是最小化 / 全屏 / 关闭三个按钮，
空白处按住可以拖窗口。这就是"去掉 pygame 那个系统标题头"之后该补上的东西，
不补的话无边框只是"更难用"而不是"更好看"。

拖动当前只在 Windows 上实现（SDL 没有暴露"移动窗口"的接口，只能借一下
``WM_NCLBUTTONDOWN`` + ``HTCAPTION``）；别的平台退化成"拖不动"，
其余按钮照常可用 —— 不会抛异常，也不会卡住。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field

import pygame

from boardgames.ui import render, theme
from boardgames.ui.fonts import FontBook

#: 标题栏高度（无边框模式下从窗口顶部扣掉这么多给标题栏）
TITLEBAR_H = 34
#: 右侧按钮
BTN_W, BTN_H = 46, 26
BTN_GAP = 4
BTN_MARGIN = 8

#: 三种按钮的绘制样式
MINIMIZE, MAXIMIZE, CLOSE = "minimize", "maximize", "close"


@dataclass
class _ChromeButton:
    kind: str
    action: Callable[[], None]
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    hovered: bool = False

    def draw(self, surface: pygame.Surface, fullscreen: bool) -> None:
        if self.kind == CLOSE:
            bg = theme.BAD if self.hovered else None
            fg = (255, 255, 255) if self.hovered else theme.TEXT_DIM
        else:
            bg = theme.PANEL_HOVER if self.hovered else None
            fg = theme.TEXT if self.hovered else theme.TEXT_DIM
        if bg is not None:
            render.rounded_rect(surface, self.rect, bg, theme.RADIUS_SM)
        cx, cy = self.rect.center

        if self.kind == MINIMIZE:
            pygame.draw.line(surface, fg, (cx - 5, cy + 4), (cx + 5, cy + 4), 1)
        elif self.kind == MAXIMIZE:
            if fullscreen:
                # 还原：两个错开的方框
                pygame.draw.rect(surface, fg, pygame.Rect(cx - 5, cy - 1, 8, 8), 1)
                pygame.draw.rect(surface, fg, pygame.Rect(cx - 1, cy - 5, 8, 8), 1)
            else:
                pygame.draw.rect(surface, fg, pygame.Rect(cx - 5, cy - 5, 11, 11), 1)
        else:  # CLOSE
            pygame.draw.line(surface, fg, (cx - 4, cy - 4), (cx + 4, cy + 4), 1)
            pygame.draw.line(surface, fg, (cx + 4, cy - 4), (cx - 4, cy + 4), 1)


class TitleBar:
    """程序自绘的标题栏：标题 + 三个按钮 + 拖动。"""

    def __init__(
        self,
        title: str = "棋类游戏",
        *,
        on_close: Callable[[], None] | None = None,
        on_minimize: Callable[[], None] | None = None,
        on_maximize: Callable[[], None] | None = None,
    ) -> None:
        self.title = title
        self.fullscreen = False
        self.hovered = False
        self.rect = pygame.Rect(0, 0, theme.WINDOW_W, TITLEBAR_H)
        self._buttons = [
            _ChromeButton(MINIMIZE, on_minimize or (lambda: None)),
            _ChromeButton(MAXIMIZE, on_maximize or (lambda: None)),
            _ChromeButton(CLOSE, on_close or (lambda: None)),
        ]

    # ------------------------------------------------------------------ #
    # 布局 / 状态
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self.rect = pygame.Rect(area.x, area.y, area.width, TITLEBAR_H)
        right = self.rect.right - BTN_MARGIN
        for button in reversed(self._buttons):  # 从右往左排
            button.rect = pygame.Rect(
                right - BTN_W, self.rect.centery - BTN_H // 2, BTN_W, BTN_H
            )
            right = button.rect.x - BTN_GAP

    def set_title(self, title: str) -> None:
        self.title = title

    def _button_at(self, pos) -> _ChromeButton | None:
        for button in self._buttons:
            if button.rect.collidepoint(pos):
                return button
        return None

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def handle_event(self, event: pygame.event.Event) -> bool:
        """只消费**落在标题栏里**的鼠标事件，其余一律放行给场景。"""
        pos = getattr(event, "pos", None)
        if event.type == pygame.MOUSEMOTION and pos is not None:
            inside = self.rect.collidepoint(pos)
            self.hovered = inside
            hit = self._button_at(pos) if inside else None
            for button in self._buttons:
                button.hovered = button is hit
            return False  # 悬停不拦截，场景照常收到

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and pos is not None:
            if not self.rect.collidepoint(pos):
                return False
            hit = self._button_at(pos)
            if hit is not None:
                return True  # 等到松手再触发，和 Button 的"按下 + 松开都在按钮上"一致
            _start_window_drag()
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and pos is not None:
            if not self.rect.collidepoint(pos):
                return False
            hit = self._button_at(pos)
            if hit is not None:
                hit.action()
            return True
        return False

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        bar = self.rect
        render.rounded_rect(surface, bar, theme.BG_ALT, 0)
        pygame.draw.line(surface, theme.BORDER_SOFT,
                         (bar.x, bar.bottom - 1), (bar.right, bar.bottom - 1))

        # 左侧的小色块：纯装饰，让这条不像"多出来的一行"
        dot = pygame.Rect(bar.x + 12, bar.centery - 5, 10, 10)
        render.rounded_rect(surface, dot, theme.ACCENT, 3)
        render.text(surface, fonts.get(13), self.title,
                    (dot.right + 10, bar.centery), theme.TEXT_DIM, baseline="middle")

        for button in self._buttons:
            button.draw(surface, self.fullscreen)


def _start_window_drag() -> None:
    """让系统接管"拖标题栏"这件事（目前只有 Windows 能借到这个能力）。

    SDL 没有暴露设置窗口位置的接口，所以只能给窗口发一条
    ``WM_NCLBUTTONDOWN / HTCAPTION`` —— 效果和真的按住系统标题栏一样。
    任何异常都吞掉：拖不动最多是不方便，不该让程序崩。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        info = pygame.display.get_wm_info()
        hwnd = info.get("window") if isinstance(info, dict) else None
        if not hwnd:
            return
        WM_NCLBUTTONDOWN = 0x00A1
        HTCAPTION = 0x0002
        ctypes.windll.user32.ReleaseCapture()
        ctypes.windll.user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception:  # pragma: no cover - 只在真机上才会走到
        pass
