"""自绘控件基类。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from boardgames.ui.fonts import FontBook


class Widget:
    """所有控件的基类。

    ``handle_event`` 返回 ``True`` 表示事件已被消费（不再向下冒泡）。
    """

    def __init__(self, key: str = "", label: str = "") -> None:
        self.key = key
        self.label = label
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.enabled = True
        self.visible = True
        self.hovered = False
        self.pressed = False

    # ---- 布局 ----

    def layout(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)

    @property
    def height(self) -> int:
        return 0

    # ---- 交互 ----

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        self.hovered = self.visible and self.enabled and self.rect.collidepoint(mouse)

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        raise NotImplementedError

    # ---- 便捷 ----

    def _mouse_pos(self) -> tuple[int, int]:
        return pygame.mouse.get_pos()


class ValueWidget(Widget):
    """带值的控件基类（滑块 / 开关 / 下拉）。"""

    def __init__(
        self,
        key: str,
        label: str,
        value: Any,
        on_change: Callable[[str, Any], None] | None = None,
    ) -> None:
        super().__init__(key, label)
        self._value = value
        self.on_change = on_change

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, new_value: Any) -> None:
        if new_value != self._value:
            self._value = new_value
            if self.on_change is not None:
                self.on_change(self.key, new_value)

    def set_value_silently(self, new_value: Any) -> None:
        self._value = new_value
