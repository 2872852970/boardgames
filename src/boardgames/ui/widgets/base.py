"""自绘控件基类。"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pygame

from boardgames.ui import theme
from boardgames.ui.fonts import FontBook

#: 行右侧为「恢复初始值」↺ 预留的宽度（控件自己的右端元素要让出这么多）
RESET_W = 26
#: ↺ 的点击区边长
RESET_SIZE = 22


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
    """带值的控件基类（滑块 / 开关 / 下拉）。

    「恢复初始值」
    --------------
    构造时传入 ``default`` 就自动获得行右侧那个小 ↺：

    * 只有**当前值确实被改过**（``has_reset``）时才亮成可点，没改过就只占位；
    * 点击 = 恢复默认值，并且**走 ``on_change``**（所以照样写回设置、
      并触发该有的"重开一局 / 重开搜索"）；
    * ↺ 的横向位置由 :data:`RESET_W` 决定，**控件自己的右端元素必须让出这么多**
      （见各控件的 ``value_box`` / ``_switch`` / ``_box``）——
      这样 ↺ 亮起或熄灭都不会让同行元素左右跳；
    * ``↺`` 字形在部分中文字体里是缺字，所以图标是**画**出来的
      （弧 + 箭头，理由同 :func:`boardgames.ui.render.disclosure_arrow`）。
    """

    def __init__(
        self,
        key: str,
        label: str,
        value: Any,
        on_change: Callable[[str, Any], None] | None = None,
        *,
        default: Any = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(key, label)
        self._value = value
        self.on_change = on_change
        #: 该项的默认值；``None`` 表示"这一项不支持恢复初始值"
        self.default = default
        self.on_reset = on_reset
        self._reset_hovered = False

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

    # ---- 恢复初始值 ----

    @property
    def supports_reset(self) -> bool:
        return self.default is not None

    @property
    def has_reset(self) -> bool:
        """当前值和默认值不一样（= 这一项被改过）。"""
        return self.supports_reset and self._value != self.default

    @property
    def _reset_center(self) -> tuple[int, int]:
        """↺ 的中心。默认在行的垂直中点，各控件按自己的右端元素对齐覆盖它。"""
        return (self.rect.right - RESET_SIZE // 2 - 2, self.rect.centery)

    @property
    def reset_rect(self) -> pygame.Rect:
        cx, cy = self._reset_center
        return pygame.Rect(cx - RESET_SIZE // 2, cy - RESET_SIZE // 2, RESET_SIZE, RESET_SIZE)

    def reset(self) -> None:
        """恢复默认值（走 ``on_change``，因此会写回设置并触发必要的重开）。

        ``on_reset`` 那条路只负责**写回设置**，不会反过来更新控件自己 ——
        所以这里要把本控件的值也同步成默认值，否则会出现"设置里已经是 4、
        界面上还写着 7、↺ 还亮着"的错位。
        """
        if not self.supports_reset:
            return
        if self.on_reset is not None:
            self.on_reset()
            self.set_value_silently(self.default)
        else:
            self.value = self.default

    def handle_reset(self, event: pygame.event.Event) -> bool:
        """点中 ↺ 就恢复默认值并吃掉事件。

        各控件的 ``handle_event`` 里**必须先调它** —— ↺ 落在行的右端，
        而滑块这类活动区是覆盖整行的，不先拦就会被当成"拖到最右"。
        """
        if not (self.visible and self.enabled and self.has_reset):
            return False
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.reset_rect.collidepoint(event.pos)
        ):
            self.reset()
            return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        self._reset_hovered = (
            self.enabled and self.has_reset and self.reset_rect.collidepoint(mouse)
        )

    def draw_reset(self, surface: pygame.Surface) -> None:
        """画 ↺（没被改过时只留一个很淡的占位）。

        用**采样折线 + 切线箭头**自己画，不用 ``pygame.draw.arc``：后者的角度
        与"屏幕上看过去的方向"是反的（y 轴朝下），画出来的弧常常只剩半圈，
        看着像个乱码。折线还能精确控制缺口留在哪 —— 缺口留给箭头。
        """
        if not self.supports_reset:
            return
        if not self.has_reset:
            color = theme.mix(theme.PANEL_ALT, theme.TEXT_FAINT, 0.30)
        elif self._reset_hovered:
            color = theme.ACCENT_HOVER
        else:
            color = theme.TEXT_DIM
        cx, cy = self._reset_center
        radius = 7
        steps = 22
        start = math.radians(62)      # 缺口留在右上，箭头补在那里
        sweep = math.radians(-308)    # 顺时针扫一圈差一个缺口
        points = [
            (cx + radius * math.cos(start + sweep * i / steps),
             cy - radius * math.sin(start + sweep * i / steps))
            for i in range(steps + 1)
        ]
        pygame.draw.lines(surface, color, False, points, 2)
        # 箭头：沿折线端点处的切线方向，不依赖角度正负号的推理
        tip, nxt = points[0], points[3]
        dx, dy = tip[0] - nxt[0], tip[1] - nxt[1]
        length = math.hypot(dx, dy) or 1.0
        dx, dy = dx / length, dy / length
        px, py = -dy, dx
        pygame.draw.polygon(surface, color, [
            (tip[0] + dx * 5.0, tip[1] + dy * 5.0),
            (tip[0] + px * 4.5, tip[1] + py * 4.5),
            (tip[0] - px * 4.5, tip[1] - py * 4.5),
        ])
