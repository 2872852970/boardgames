"""具体控件：按钮、滑块、下拉、开关、分段选择、文本。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pygame

from boardgames.ui import render, theme
from boardgames.ui.animation import ease_out_cubic, lerp
from boardgames.ui.fonts import FontBook
from boardgames.ui.widgets.base import RESET_W, ValueWidget, Widget

ROWH = 30
LABEL_H = 22


def _fmt_number(value: float) -> str:
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:g}"


# --------------------------------------------------------------------------- #
# 按钮
# --------------------------------------------------------------------------- #

class Button(Widget):
    def __init__(
        self,
        label: str,
        on_click: Callable[[], None],
        *,
        key: str = "",
        variant: str = "ghost",
        enabled: bool = True,
    ) -> None:
        super().__init__(key, label)
        self.on_click = on_click
        self.variant = variant
        self.enabled = enabled
        self._press_t = 1.0

    @property
    def height(self) -> int:
        return 36

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            if was and self.rect.collidepoint(event.pos):
                self._press_t = 0.0
                self.on_click()
                return True
            if was:
                return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        if self._press_t < 1.0:
            self._press_t = min(1.0, self._press_t + dt_ms / 90.0)

    def _colors(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        if not self.enabled:
            return theme.PANEL_ALT, theme.TEXT_FAINT
        if self.variant == "primary":
            base = theme.ACCENT_HOVER if self.hovered else theme.ACCENT
            return base, (255, 255, 255)
        if self.variant == "danger":
            base = theme.mix(theme.BAD, (0, 0, 0), 0.25) if self.hovered else theme.darken(theme.BAD, 0.45)
            return base, theme.TEXT
        base = theme.PANEL_HOVER if self.hovered else theme.PANEL_ALT
        return base, theme.TEXT

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        bg, fg = self._colors()
        # 轻微的下压反馈
        shrink = int(ease_out_cubic(self._press_t) * 0)
        rect = self.rect.inflate(-shrink, -shrink)
        render.rounded_rect(surface, rect, bg, theme.RADIUS_SM)
        if self.variant == "ghost":
            render.rounded_rect(surface, rect, theme.BORDER, theme.RADIUS_SM, width=1)
        if self._press_t < 1.0:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            alpha = int((1.0 - self._press_t) * 70)
            render.rounded_rect(overlay, pygame.Rect(0, 0, *rect.size), (*theme.ACCENT, alpha), theme.RADIUS_SM)
            surface.blit(overlay, rect.topleft)
        # 按钮很窄时（如最小侧栏下 6 个底栏按钮）降一档字号，
        # 否则中文两字会顶到边框
        size = 14
        if fonts.get(14).size(self.label)[0] > rect.width - 8:
            size = 12
        render.text(surface, fonts.get(size), self.label, rect.center, fg,
                    align="center", baseline="middle")


# --------------------------------------------------------------------------- #
# 滑块
# --------------------------------------------------------------------------- #

class Slider(ValueWidget):
    """带可编辑数值框的滑块。

    拖动滑轨调节，或**点击右侧数值框直接键入**数值（回车确认 / Esc 取消）。
    """

    def __init__(
        self,
        key: str,
        label: str,
        value: float,
        minimum: float,
        maximum: float,
        step: float = 1.0,
        on_change: Callable[[str, Any], None] | None = None,
        *,
        fmt: Callable[[float], str] = _fmt_number,
        on_edit: Callable[[Slider], None] | None = None,
        default: float | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(key, label, float(value), on_change,
                         default=default, on_reset=on_reset)
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        self.step = float(step) if step else 0.0
        self.fmt = fmt
        self.on_edit = on_edit
        self.editing = False
        self._buffer = ""
        self._dragging = False
        self._box_hovered = False
        self._caret_t = 0.0
        #: 整数参数不允许输入小数点
        self._decimal = bool(self.step) and float(self.step) != int(self.step)

    @property
    def height(self) -> int:
        return 48

    @property
    def _track(self) -> pygame.Rect:
        return pygame.Rect(self.rect.x, self.rect.y + 32, self._track_width, 6)

    @property
    def _track_width(self) -> int:
        """滑轨宽度：右端要让出「恢复初始值」那一格。"""
        return max(40, self.rect.width - (RESET_W if self.supports_reset else 0))

    @property
    def value_box(self) -> pygame.Rect:
        """可点击输入的数值框区域。"""
        width = 80
        right = self.rect.right - (RESET_W if self.supports_reset else 0)
        return pygame.Rect(right - width, self.rect.y - 1, width, 24)

    @property
    def _reset_center(self) -> tuple[int, int]:
        # 和数值框同一行居中：↺ 挨着数值框，而不是压到下面的滑轨上
        return (self.rect.right - RESET_W // 2 - 2, self.value_box.centery)

    def _knob_x(self) -> int:
        span = max(1.0, self.maximum - self.minimum)
        t = (self.value - self.minimum) / span
        return int(self._track.x + t * self._track.width)

    def _value_at(self, x: int) -> float:
        t = (x - self._track.x) / max(1, self._track.width)
        raw = self.minimum + max(0.0, min(1.0, t)) * (self.maximum - self.minimum)
        if self.step:
            raw = self.minimum + round((raw - self.minimum) / self.step) * self.step
        return max(self.minimum, min(self.maximum, raw))

    # ---- 直接输入数值 ----

    def begin_edit(self) -> None:
        self.editing = True
        self._buffer = self.fmt(self.value)
        self._dragging = False
        if self.on_edit is not None:
            self.on_edit(self)

    def cancel_edit(self) -> None:
        self.editing = False
        self._buffer = ""

    def commit_edit(self) -> None:
        text = self._buffer.strip()
        self.editing = False
        self._buffer = ""
        if not text or text in {"-", ".", "-."}:
            return
        try:
            raw = float(text)
        except ValueError:
            return
        # 手动输入只做范围裁剪，不按步长取整（否则输入 8 会被吸到 7 这类意外）
        self.value = max(self.minimum, min(self.maximum, raw))

    def _accepts(self, char: str) -> bool:
        if char.isdigit():
            return True
        if char == "." and self._decimal:
            return "." not in self._buffer
        if char == "-" and self.minimum < 0:
            return "-" not in self._buffer
        return False

    def handle_key(self, event: pygame.event.Event) -> bool:
        """编辑状态下接管键盘；返回 True 表示事件已被消费。"""
        if not self.editing:
            return False
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            self.commit_edit()
            return True
        if event.key == pygame.K_ESCAPE:
            self.cancel_edit()
            return True
        if event.key == pygame.K_BACKSPACE:
            self._buffer = self._buffer[:-1]
            return True
        char = event.unicode
        if char == "，":  # 中文输入法下的全角句点
            char = "."
        if char and self._accepts(char):
            self._buffer += char
        return True

    # ---- 交互 ----

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if self.handle_reset(event):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.value_box.collidepoint(event.pos):
                self.begin_edit()
                return True
            if self.rect.inflate(0, 6).collidepoint(event.pos):
                self._dragging = True
                self.value = self._value_at(event.pos[0])
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # 抬起事件必须无条件结束拖拽，否则会在侧栏外松手时卡住
            was_dragging = self._dragging
            self._dragging = False
            return was_dragging
        if event.type == pygame.MOUSEMOTION and self._dragging:
            # 只有真正按住左键拖拽时才跟随鼠标
            self.value = self._value_at(event.pos[0])
            return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        self._box_hovered = self.enabled and self.value_box.collidepoint(mouse)
        if self.editing:
            self._caret_t += dt_ms / 1000.0
        # 兜底：鼠标抬起事件被别处吞掉时，也能用按键状态解除拖拽。
        # 否则滑块会"卡在拖拽态"，之后不按键鼠标一动就改数值。
        if self._dragging:
            try:
                held = pygame.mouse.get_pressed()[0]
            except pygame.error:  # 没有初始化视频系统
                held = True
            if not held:
                self._dragging = False

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        box = self.value_box
        label_font = fonts.get(13)
        render.text(
            surface,
            label_font,
            render.truncate(label_font, self.label, max(20, self.rect.width - box.width - RESET_W - 12)),
            (self.rect.x, self.rect.y + 2),
            theme.TEXT_DIM,
        )

        # 数值框：点一下就能直接输入
        if self.editing:
            box_bg, box_border = theme.BG, theme.ACCENT
        elif self._box_hovered:
            box_bg, box_border = theme.PANEL_HOVER, theme.ACCENT_DIM
        else:
            box_bg, box_border = theme.PANEL_ALT, theme.BORDER_SOFT
        render.rounded_rect(surface, box, box_bg, theme.RADIUS_SM)
        render.rounded_rect(surface, box, box_border, theme.RADIUS_SM, width=1)

        shown = self._buffer if self.editing else self.fmt(self.value)
        highlighted = self.editing or self.hovered or self._dragging
        color = theme.ACCENT_HOVER if highlighted else theme.TEXT
        text_rect = render.text(surface, fonts.get(13), shown, (box.right - 8, box.centery), color,
                                align="right", baseline="middle")
        if self.editing and (self._caret_t * 2) % 2 < 1.4:
            caret_x = min(text_rect.right + 2, box.right - 5)
            pygame.draw.line(surface, theme.ACCENT_HOVER, (caret_x, box.y + 4),
                             (caret_x, box.bottom - 5), 2)

        track = self._track
        render.rounded_rect(surface, track, theme.PANEL_ALT, theme.RADIUS_PILL)
        knob_x = self._knob_x()
        filled = pygame.Rect(track.x, track.y, max(0, knob_x - track.x), track.height)
        render.rounded_rect(surface, filled, theme.ACCENT_DIM, theme.RADIUS_PILL)
        radius = 8 if (self.hovered or self._dragging) else 7
        pygame.draw.circle(surface, theme.ACCENT if not self._dragging else theme.ACCENT_HOVER,
                           (knob_x, track.centery), radius)
        pygame.draw.circle(surface, theme.BG, (knob_x, track.centery), radius - 3)
        self.draw_reset(surface)


# --------------------------------------------------------------------------- #
# 开关
# --------------------------------------------------------------------------- #

class Toggle(ValueWidget):
    def __init__(
        self,
        key: str,
        label: str,
        value: bool,
        on_change: Callable[[str, Any], None] | None = None,
        *,
        default: bool | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(key, label, bool(value), on_change,
                         default=None if default is None else bool(default),
                         on_reset=on_reset)
        self._anim = 1.0 if value else 0.0

    @property
    def height(self) -> int:
        return 40

    @property
    def _switch(self) -> pygame.Rect:
        w, h = 42, 22
        right = self.rect.right - (RESET_W if self.supports_reset else 0)
        return pygame.Rect(right - w, self.rect.y + 8, w, h)

    @property
    def _reset_center(self) -> tuple[int, int]:
        return (self.rect.right - RESET_W // 2 - 2, self._switch.centery)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if self.handle_reset(event):
            return True
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            self.value = not self.value
            return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        target = 1.0 if self.value else 0.0
        self._anim = lerp(self._anim, target, min(1.0, dt_ms / 90.0))

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        switch = self._switch
        render.text(
            surface, fonts.get(14),
            render.truncate(fonts.get(14), self.label,
                            max(20, switch.left - self.rect.x - RESET_W - 8)),
            (self.rect.x, self.rect.centery), theme.TEXT, baseline="middle",
        )
        t = ease_out_cubic(self._anim)
        bg = theme.mix(theme.PANEL_ALT, theme.ACCENT, t)
        render.rounded_rect(surface, switch, bg, theme.RADIUS_PILL)
        knob_x = int(lerp(switch.x + 11, switch.right - 11, t))
        pygame.draw.circle(surface, (255, 255, 255), (knob_x, switch.centery), 8)
        self.draw_reset(surface)


# --------------------------------------------------------------------------- #
# 下拉
# --------------------------------------------------------------------------- #

class Dropdown(ValueWidget):
    def __init__(
        self,
        key: str,
        label: str,
        value: str,
        choices: Sequence[str],
        on_change: Callable[[str, Any], None] | None = None,
        *,
        labels: dict[str, str] | None = None,
        default: str | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(key, label, value, on_change, default=default, on_reset=on_reset)
        self.choices = list(choices)
        self.labels = dict(labels or {})
        self.open = False
        self._hover_index = -1

    @property
    def height(self) -> int:
        return 62 if self.label else 38

    def display(self, value: str | None = None) -> str:
        value = self.value if value is None else value
        return self.labels.get(value, value)

    @property
    def _box(self) -> pygame.Rect:
        top = self.rect.y + (LABEL_H if self.label else 0)
        right = self.rect.right - (RESET_W if self.supports_reset else 0)
        return pygame.Rect(self.rect.x, top, max(40, right - self.rect.x), 38)

    @property
    def _reset_center(self) -> tuple[int, int]:
        return (self.rect.right - RESET_W // 2 - 2, self._box.centery)

    def _option_rects(self) -> list[pygame.Rect]:
        out = []
        box = self._box
        top = box.bottom + 4
        for i in range(len(self.choices)):
            out.append(pygame.Rect(box.x, top + i * 32, box.width, 30))
        return out

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        # 展开列表优先接管（点选项 / 点别处 = 收起），此时 ↺ 不参与
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.open:
                for choice, rect in zip(self.choices, self._option_rects(), strict=True):
                    if rect.collidepoint(event.pos):
                        self.open = False
                        self.value = choice
                        return True
                self.open = False
                return self._box.collidepoint(event.pos) or True
            if self.handle_reset(event):
                return True
            if self._box.collidepoint(event.pos):
                self.open = True
                return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        self._hover_index = -1
        if self.open:
            for i, rect in enumerate(self._option_rects()):
                if rect.collidepoint(mouse):
                    self._hover_index = i
                    break

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        if self.label:
            render.text(surface, fonts.get(13), self.label, (self.rect.x, self.rect.y + 2), theme.TEXT_DIM)
        box = self._box
        bg = theme.PANEL_HOVER if (self.hovered or self.open) else theme.PANEL_ALT
        render.rounded_rect(surface, box, bg, theme.RADIUS_SM)
        render.rounded_rect(surface, box, theme.BORDER, theme.RADIUS_SM, width=1)
        render.text(surface, fonts.get(14), render.truncate(fonts.get(14), self.display(), box.width - 46),
                    (box.x + 12, box.centery), theme.TEXT, baseline="middle")
        arrow = "▲" if self.open else "▼"
        render.text(surface, fonts.get(11), arrow, (box.right - 12, box.centery), theme.TEXT_DIM,
                    align="right", baseline="middle")
        self.draw_reset(surface)

    def draw_overlay(self, surface: pygame.Surface, fonts: FontBook) -> None:
        """展开的列表必须在所有控件之上绘制。"""
        if not self.open or not self.visible:
            return
        rects = self._option_rects()
        if not rects:
            return
        panel_rect = rects[0].union(rects[-1]).inflate(0, 8)
        render.soft_shadow(surface, panel_rect, theme.RADIUS_SM, spread=3)
        render.rounded_rect(surface, panel_rect, theme.PANEL_ALT, theme.RADIUS_SM)
        render.rounded_rect(surface, panel_rect, theme.BORDER, theme.RADIUS_SM, width=1)
        for i, (choice, rect) in enumerate(zip(self.choices, rects, strict=True)):
            if i == self._hover_index:
                render.rounded_rect(surface, rect.inflate(-6, 0), theme.PANEL_HOVER, theme.RADIUS_SM)
            color = theme.ACCENT_HOVER if choice == self.value else theme.TEXT
            render.text(surface, fonts.get(14), self.display(choice), (rect.x + 12, rect.centery), color,
                        baseline="middle")


# --------------------------------------------------------------------------- #
# 分段选择
# --------------------------------------------------------------------------- #

class Segmented(ValueWidget):
    def __init__(
        self,
        key: str,
        label: str,
        value: str,
        choices: Sequence[str],
        on_change: Callable[[str, Any], None] | None = None,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__(key, label, value, on_change)
        self.choices = list(choices)
        self.labels = dict(labels or {})
        self._hover_index = -1

    @property
    def height(self) -> int:
        return 64 if self.label else 40

    def display(self, value: str) -> str:
        return self.labels.get(value, value)

    @property
    def _strip(self) -> pygame.Rect:
        top = self.rect.y + (LABEL_H if self.label else 0)
        return pygame.Rect(self.rect.x, top, self.rect.width, 36)

    def _cell(self, index: int) -> pygame.Rect:
        strip = self._strip
        width = strip.width // len(self.choices)
        return pygame.Rect(strip.x + index * width, strip.y, width, strip.height)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, choice in enumerate(self.choices):
                if self._cell(i).collidepoint(event.pos):
                    self.value = choice
                    return True
        return False

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        super().update(dt_ms, mouse)
        self._hover_index = -1
        for i in range(len(self.choices)):
            if self._cell(i).collidepoint(mouse):
                self._hover_index = i
                break

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        if self.label:
            render.text(surface, fonts.get(13), self.label, (self.rect.x, self.rect.y + 2), theme.TEXT_DIM)
        strip = self._strip
        render.rounded_rect(surface, strip, theme.PANEL_ALT, theme.RADIUS_SM)
        for i, choice in enumerate(self.choices):
            cell = self._cell(i)
            selected = choice == self.value
            if selected:
                render.rounded_rect(surface, cell.inflate(-3, -4), theme.ACCENT, theme.RADIUS_SM)
            elif i == self._hover_index:
                render.rounded_rect(surface, cell.inflate(-3, -4), theme.PANEL_HOVER, theme.RADIUS_SM)
            color = (255, 255, 255) if selected else theme.TEXT_DIM
            render.text(surface, fonts.get(13), self.display(choice), cell.center, color,
                        align="center", baseline="middle")


# --------------------------------------------------------------------------- #
# 文本
# --------------------------------------------------------------------------- #

class Label(Widget):
    def __init__(self, text_value: str, *, size: int = 14, color: tuple[int, int, int] = theme.TEXT,
                 align: str = "left", key: str = "", dynamic: bool = False) -> None:
        super().__init__(key, text_value)
        self.text_value = text_value
        self.size = size
        self.color = color
        self.align = align
        self.dynamic = dynamic

    @property
    def height(self) -> int:
        return self.size + 8

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        if self.align == "center":
            render.text(surface, fonts.get(self.size), self.text_value, self.rect.center, self.color,
                        align="center", baseline="middle")
        elif self.align == "right":
            render.text(surface, fonts.get(self.size), self.text_value, (self.rect.right, self.rect.centery),
                        self.color, align="right", baseline="middle")
        else:
            render.text(surface, fonts.get(self.size), self.text_value, (self.rect.x, self.rect.centery),
                        self.color, baseline="middle")


class SectionHeader(Widget):
    def __init__(self, title: str) -> None:
        super().__init__("", title)

    @property
    def height(self) -> int:
        return 32

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self.visible:
            return
        render.text(surface, fonts.get(12), self.label, (self.rect.x, self.rect.centery), theme.TEXT_FAINT,
                    baseline="middle")
        line_x = self.rect.x + fonts.get(12).size(self.label)[0] + 10
        if line_x < self.rect.right:
            pygame.draw.line(surface, theme.BORDER_SOFT, (line_x, self.rect.centery),
                             (self.rect.right, self.rect.centery), 1)
