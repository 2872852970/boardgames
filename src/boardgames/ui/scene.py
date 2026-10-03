"""场景抽象：大厅 ↔ 对局之间切换的最小接口。

:class:`~boardgames.ui.window.GameWindow` 只负责"窗口宿主"这一件事 ——
screen / 时钟 / QUIT / VIDEORESIZE / 设置落盘。**具体画什么、响应什么**
全部交给当前场景。

这样做的好处是窗口不再关心"现在处于哪个界面"；将来加"复盘""设置"
这类界面只要再实现一个 Scene，不用碰主循环。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pygame

from boardgames.ui.fonts import FontBook


@runtime_checkable
class Scene(Protocol):
    """一个可切换的界面。"""

    def on_enter(self) -> None:
        """切入本场景时调用（重建内部状态、刷新标题等）。"""

    def on_exit(self) -> None:
        """离开本场景时调用（停掉后台线程、AI 搜索等）。"""

    def layout(self, area: pygame.Rect) -> None:
        """窗口尺寸变化时重新计算布局。"""

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理一个事件；返回 True 表示已消费。"""

    def update(self, dt_ms: float) -> None:
        """推进一帧逻辑。"""

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        """整屏绘制。"""
