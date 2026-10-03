"""右侧控制面板：对局状态、操作按钮、参数调节。

面板结构（自上而下）：

* 固定头部：游戏名 + 对局模式切换 + 回合指示
* 可滚动区：双方信息、AI 状态、分组参数（**按当前模式自动精简**）
* 固定底栏：新局 / 悔棋 /（自对弈时）暂停 / 认输

「按模式精简」规则：

* 双人对战：只留棋局设置与界面参数，AI 相关分组全部隐藏；
* 人机 / 自对弈：只显示**实际参战**的引擎参数（Minimax 或 MCTS），
  以及评估权重（随机走子没有可调项，所以什么都不显示）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pygame

from boardgames.settings import (
    GROUPS,
    MODE_LABELS,
    PLAYER_TYPE_LABELS,
    SPEC_BY_KEY,
    SPECS,
    Settings,
)
from boardgames.ui import render, theme
from boardgames.ui.animation import pulse
from boardgames.ui.fonts import FontBook
from boardgames.ui.widgets import Button, Dropdown, Segmented, Slider, Toggle, Widget

HEADER_H = 178
FOOTER_H = 64
SCROLL_STEP = 56

# 头部各元素的纵向位置（相对面板顶部）
TITLE_Y = 12
SUBTITLE_Y = 44
MODE_Y = 64
PLAYERS_Y = 112
PLAYER_ROW_H = 26


@dataclass
class Status:
    """由主循环每帧刷新的运行时信息。"""

    current_player: int | None = None
    player_types: tuple[str, str] = ("human", "human")
    walls_left: tuple[int, int] = (10, 10)
    #: 每方的自定义详情（**只放数值部分**，如 "墙 10" / "已落 12 子"）；
    #: 类型标签由侧栏自己拼上去。留空则回退到 ``walls_left``。
    player_details: tuple[str, str] = ("", "")
    is_thinking: bool = False
    thinking_player: int = 0
    thinking_elapsed_ms: float = 0.0
    last_search: str = ""
    winner_text: str = ""
    is_over: bool = False
    paused: bool = False
    can_undo: bool = True
    hint: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Section:
    group_id: str
    title: str
    expanded: bool
    widgets: list[Widget] = field(default_factory=list)


class Sidebar:
    """控制面板。"""

    def __init__(
        self,
        settings: Settings,
        on_setting: Callable[[str, Any], None],
        on_action: Callable[[str, Any], None],
        *,
        game_key: str = "quoridor",
        game_title: str = "步步为营",
        game_tagline: str = "Quoridor · 墙棋",
    ) -> None:
        self.settings = settings
        self.on_setting = on_setting
        self.on_action = on_action
        self.game_key = game_key
        self.game_title = game_title
        self.game_tagline = game_tagline
        self.rect = pygame.Rect(0, 0, theme.SIDEBAR_W, theme.WINDOW_H)
        self.scroll = 0.0
        self.max_scroll = 0.0
        self.status = Status()
        self._time = 0.0
        self.sections: list[_Section] = []
        self.footer_buttons: list[Button] = []
        self._mode_widget: Segmented | None = None
        self._content_x = 0
        self._content_w = 0
        self._header_rects: dict[str, pygame.Rect] = {}
        self._players_rect: pygame.Rect | None = None
        self._thinking_rect: pygame.Rect | None = None
        #: 当前正在接受键盘输入的数值框
        self._editing: Slider | None = None
        self._build()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        expanded = {
            "game": False,
            "players": True,
            "minimax": True,
            "mcts": True,
            "eval": False,
            "ui": False,
        }
        by_group: dict[str, list[Widget]] = {gid: [] for gid, _ in GROUPS}
        for spec in SPECS:
            if not spec.expose or spec.key == "mode":
                continue  # mode 放在固定头部，不参与滚动区
            widget = self._make_widget(spec)
            if widget is not None:
                by_group[spec.group].append(widget)

        self.sections = [
            _Section(gid, title, expanded.get(gid, False), by_group[gid])
            for gid, title in GROUPS
            if by_group[gid]
        ]

        mode_spec = next(s for s in SPECS if s.key == "mode")
        self._mode_widget = Segmented(
            mode_spec.key, "", self.settings.get("mode"), mode_spec.choices,
            self.on_setting, labels=MODE_LABELS,
        )

        self.footer_buttons = [
            Button("新局", lambda: self.on_action("new_game", None), variant="primary"),
            Button("悔棋", lambda: self.on_action("undo", None), key="undo"),
            Button("单步", lambda: self.on_action("step", None), key="step"),
            Button("暂停", lambda: self.on_action("toggle_pause", None), key="pause"),
            Button("大厅", lambda: self.on_action("lobby", None), key="lobby"),
            Button("认输", lambda: self.on_action("resign", None), variant="danger", key="resign"),
        ]

    def _make_widget(self, spec) -> Widget | None:
        value = self.settings.get(spec.key)
        labels = PLAYER_TYPE_LABELS if spec.key in {"p1_type", "p2_type"} else None
        if spec.kind == "bool":
            return Toggle(spec.key, spec.label, bool(value), self.on_setting)
        if spec.kind == "int":
            return Slider(
                spec.key, spec.label, value,
                spec.minimum or 0, spec.maximum or 0, spec.step or 1,
                self.on_setting, fmt=lambda v: str(int(round(v))), on_edit=self._begin_edit,
            )
        if spec.kind == "float":
            return Slider(
                spec.key, spec.label, value,
                spec.minimum or 0, spec.maximum or 0, spec.step or 0.01,
                self.on_setting, fmt=lambda v: f"{v:g}", on_edit=self._begin_edit,
            )
        if spec.kind == "choice":
            return Dropdown(spec.key, spec.label, value, spec.choices, self.on_setting, labels=labels)
        return None

    def sync_from_settings(self) -> None:
        for section in self.sections:
            for widget in section.widgets:
                widget.set_value_silently(self.settings.get(widget.key))
        if self._mode_widget is not None:
            self._mode_widget.set_value_silently(self.settings.get("mode"))

    def set_game(self, game_key: str, title: str, tagline: str) -> None:
        """切换棋类：改标题，并让参数按新棋类重新过滤（widget 本身已建好，只需刷可见性）。"""
        self.game_key = game_key
        self.game_title = title
        self.game_tagline = tagline
        # 上一轮正在编辑的输入框可能属于新棋类里不存在的参数，直接收工
        self._end_editing(commit=True)
        self.scroll = 0.0
        self._layout_content()

    # ------------------------------------------------------------------ #
    # 数值输入框
    # ------------------------------------------------------------------ #

    def _begin_edit(self, widget: Slider) -> None:
        """某个数值框获得焦点；同时只允许一个在编辑。"""
        if self._editing is not None and self._editing is not widget:
            self._editing.commit_edit()
        self._editing = widget

    def _end_editing(self, commit: bool = True) -> None:
        widget = self._editing
        self._editing = None
        if widget is None:
            return
        if commit:
            widget.commit_edit()
        else:
            widget.cancel_edit()

    def handle_key(self, event: pygame.event.Event) -> bool:
        """键盘事件优先给正在编辑的数值框；返回 True 表示已消费。

        返回 True 时主窗口不再处理该按键 —— 否则输入 "4" 之类虽然没冲突，
        但 Esc / 字母键会误触发退出、新局、悔棋等快捷键。
        """
        widget = self._editing
        if widget is None:
            return False
        widget.handle_key(event)
        if not widget.editing:
            self._editing = None
        return True

    # ------------------------------------------------------------------ #
    # 按模式精简：哪些分组 / 参数当前有意义
    # ------------------------------------------------------------------ #

    def _ai_kinds(self) -> set[str]:
        """当前实际参战的 AI 类型（随机走子没有可调参数，但算 AI）。"""
        return {kind for kind in self.status.player_types if kind != "human"}

    def _spec_applicable(self, spec) -> bool:
        # 游戏维度过滤优先：只对某个棋类有意义的参数（墙数、列数、墙槽位…）
        # 不该在别的棋类的侧栏里露出来。
        if spec.games and self.game_key not in spec.games:
            return False
        kinds = self._ai_kinds()
        if spec.needs_engine:
            return spec.needs_engine in kinds
        if spec.needs_ai:
            return bool(kinds)
        return True

    def _widget_applicable(self, widget: Widget) -> bool:
        spec = SPEC_BY_KEY.get(widget.key)
        return True if spec is None else self._spec_applicable(spec)

    def _section_widgets(self, section: _Section) -> list[Widget]:
        return [w for w in section.widgets if self._widget_applicable(w)]

    def _section_active(self, section: _Section) -> bool:
        kinds = self._ai_kinds()
        mode = str(self.settings.get("mode"))
        gid = section.group_id
        if gid == "players":
            return mode != "pvp"
        if gid == "minimax":
            return "minimax" in kinds
        if gid == "mcts":
            return "mcts" in kinds
        if gid == "eval":
            return bool(kinds & {"minimax", "mcts"})
        return True

    def _active_sections(self) -> list[_Section]:
        return [
            section
            for section in self.sections
            if self._section_active(section) and self._section_widgets(section)
        ]

    def _visible_widgets(self) -> list[Widget]:
        out: list[Widget] = []
        for section in self._active_sections():
            if section.expanded:
                out.extend(self._section_widgets(section))
        return out

    def _show_thinking_row(self) -> bool:
        return bool(self._ai_kinds())

    def _open_dropdowns(self) -> list[Dropdown]:
        return [w for w in self._visible_widgets() if isinstance(w, Dropdown) and w.open]

    def _is_eve(self) -> bool:
        return str(self.settings.get("mode")) == "eve"

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        self._content_x = rect.x + theme.PADDING
        self._content_w = rect.width - theme.PADDING * 2
        #: 双方信息固定在头部，不随滚动移动/隐藏
        self._players_rect = pygame.Rect(
            self._content_x,
            rect.y + PLAYERS_Y,
            self._content_w,
            PLAYER_ROW_H * 2,
        )
        if self._mode_widget is not None:
            self._mode_widget.layout(self._header_mode_rect())

    @property
    def viewport(self) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x,
            self.rect.y + HEADER_H,
            self.rect.width,
            max(40, self.rect.height - HEADER_H - FOOTER_H),
        )

    def _section(self, group_id: str) -> _Section:
        for section in self.sections:
            if section.group_id == group_id:
                return section
        raise KeyError(group_id)

    def _flow(self) -> list[tuple[str, str]]:
        """滚动区的内容流（双方信息已固定在头部，不在这里）。"""
        flow: list[tuple[str, str]] = []
        if self._show_thinking_row():
            flow.append(("thinking", ""))
        for section in self._active_sections():
            flow.append(("section", section.group_id))
        return flow

    def _layout_content(self) -> None:
        top = self.viewport.y - int(self.scroll) + 10
        y = top
        self._header_rects.clear()
        self._thinking_rect = None

        for kind, gid in self._flow():
            if kind == "section":
                section = self._section(gid)
                self._header_rects[gid] = pygame.Rect(self._content_x, y, self._content_w, 30)
                y += 32
                if section.expanded:
                    for widget in self._section_widgets(section):
                        widget.visible = True
                        widget.layout(pygame.Rect(self._content_x, y, self._content_w, widget.height))
                        y += widget.height + 6
                else:
                    for widget in section.widgets:
                        widget.visible = False
                        widget.layout(pygame.Rect(0, -9000, 0, 0))
                y += 8
            else:
                self._thinking_rect = pygame.Rect(self._content_x, y, self._content_w, 34)
                y += 44

        content_h = (y - top) + 12
        self.max_scroll = max(0.0, content_h - self.viewport.height)
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))

    def _visible_footer(self) -> list[Button]:
        if self._is_eve():
            return self.footer_buttons
        return [b for b in self.footer_buttons if b.key not in ("pause", "step")]

    def _footer_button_rect(self, index: int, count: int) -> pygame.Rect:
        gap = 8
        width = (self._content_w - gap * (count - 1)) // max(1, count)
        return pygame.Rect(
            self._content_x + index * (width + gap),
            self.rect.bottom - FOOTER_H + 14,
            width,
            36,
        )

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def handle_event(self, event: pygame.event.Event) -> bool:
        mouse = getattr(event, "pos", pygame.mouse.get_pos())

        # ---- 滚轮 ----
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self._scroll_by(-event.y * SCROLL_STEP)
            return True
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button in (4, 5)
            and self.rect.collidepoint(event.pos)
        ):
            self._scroll_by(-SCROLL_STEP if event.button == 4 else SCROLL_STEP)
            return True

        # ---- 正在输入数值：点别处就确认并结束 ----
        if (
            self._editing is not None
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and not self._editing.value_box.collidepoint(event.pos)
        ):
            self._end_editing(commit=True)
            return True

        # ---- 展开中的下拉优先接管（点其它地方 = 收起） ----
        for dropdown in self._open_dropdowns():
            if dropdown.handle_event(event):
                return True

        # ---- 分组标题：只在左键按下时折叠/展开 ----
        # 不判断事件类型的话，鼠标划过标题就会每帧翻转一次。
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for gid, header in self._header_rects.items():
                if header.collidepoint(event.pos) and self.viewport.collidepoint(event.pos):
                    section = self._section(gid)
                    section.expanded = not section.expanded
                    self._layout_content()
                    return True

        # ---- 头部模式切换 ----
        if self._mode_widget is not None and self._mode_widget.handle_event(event):
            return True

        # ---- 内容区控件 ----
        # MOUSEBUTTONUP 必须无条件派发：否则在侧栏外松手会让滑块一直处于拖拽态，
        # 之后不按键鼠标一动就改数值。
        if self.viewport.collidepoint(mouse) or event.type == pygame.MOUSEBUTTONUP:
            for widget in reversed(self._visible_widgets()):
                if widget.handle_event(event):
                    return True

        # ---- 底栏 ----
        return any(button.handle_event(event) for button in self._visible_footer())

    def _scroll_by(self, delta: float) -> None:
        self.scroll += delta
        self._layout_content()

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        self._time += dt_ms / 1000.0
        self._layout_content()
        # 正在编辑的输入框被折叠 / 精简掉时，直接确认收工
        if self._editing is not None and not self._editing.visible:
            self._end_editing(commit=True)
        viewport = self.viewport
        inside = viewport.collidepoint(mouse)
        for widget in self._visible_widgets():
            widget.update(dt_ms, mouse if inside and widget.rect.colliderect(viewport) else (-1, -1))
        for button in self._visible_footer():
            button.enabled = self._footer_enabled(button)
            button.update(dt_ms, mouse)
        if self._mode_widget is not None:
            self._mode_widget.update(dt_ms, mouse)

    def _footer_enabled(self, button: Button) -> bool:
        # 按 button.key 分派（label 会被改文案，key 才是稳定标识）
        if button.key == "undo":
            return self.status.can_undo
        if button.key == "resign":
            return not self.status.is_over
        if button.key == "step":
            # 只有"暂停中"才需要单步
            return self.status.paused and not self.status.is_over
        if button.key == "pause":
            return not self.status.is_over
        return True

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def _header_mode_rect(self) -> pygame.Rect:
        return pygame.Rect(self._content_x, self.rect.y + MODE_Y, self._content_w, 36)

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        render.panel(surface, self.rect, color=theme.BG_ALT, radius=0, border=None, shadow=False)
        pygame.draw.line(surface, theme.BORDER_SOFT, (self.rect.x, self.rect.y),
                         (self.rect.x, self.rect.bottom))
        self._draw_header(surface, fonts)
        self._draw_content(surface, fonts)
        self._draw_footer(surface, fonts)
        self._draw_dropdown_overlays(surface, fonts)

    def _draw_header(self, surface: pygame.Surface, fonts: FontBook) -> None:
        render.text(surface, fonts.get(20, bold=True), self.game_title,
                    (self._content_x, self.rect.y + TITLE_Y), theme.TEXT)
        render.text(surface, fonts.get(12), self.game_tagline,
                    (self._content_x, self.rect.y + SUBTITLE_Y), theme.TEXT_FAINT)
        self._draw_turn(surface, fonts)
        if self._mode_widget is not None:
            self._mode_widget.draw(surface, fonts)
        # 双方信息固定在头部：永远可见，不会被滚动带走
        self._draw_players(surface, fonts)
        pygame.draw.line(
            surface, theme.BORDER_SOFT,
            (self.rect.x + 12, self.rect.y + HEADER_H - 6),
            (self.rect.right - 12, self.rect.y + HEADER_H - 6),
        )

    def _draw_turn(self, surface: pygame.Surface, fonts: FontBook) -> None:
        status = self.status
        text = ""
        color = theme.TEXT_DIM
        if status.is_over:
            text = status.winner_text or "对局结束"
            color = theme.WARN
        elif status.paused:
            text = "已暂停 · 可点「单步」推进" if self._is_eve() else "已暂停"
        elif status.current_player is not None:
            name = f"玩家 {status.current_player + 1}"
            color = theme.PLAYER_COLORS[status.current_player]
            if status.is_thinking and status.thinking_player == status.current_player:
                dots = "." * (1 + int(self._time * 3) % 3)
                text = f"{name} 思考中{dots}"
            else:
                text = f"轮到 {name}"
        render.text(surface, fonts.get(14), text,
                    (self.rect.right - theme.PADDING, self.rect.y + SUBTITLE_Y + 2),
                    color, align="right")

    def _draw_content(self, surface: pygame.Surface, fonts: FontBook) -> None:
        viewport = self.viewport
        previous_clip = surface.get_clip()
        surface.set_clip(viewport)

        for gid, header in self._header_rects.items():
            section = self._section(gid)
            if not header.colliderect(viewport):
                continue
            self._draw_arrow(surface, header, section.expanded)
            bold = fonts.get(13, bold=True)
            render.text(surface, bold, section.title, (header.x + 16, header.centery),
                        theme.TEXT if section.expanded else theme.TEXT_DIM, baseline="middle")
            line_x = header.x + 26 + bold.size(section.title)[0]
            if line_x < header.right:
                pygame.draw.line(surface, theme.BORDER_SOFT, (line_x, header.centery),
                                 (header.right, header.centery), 1)

        for widget in self._visible_widgets():
            if widget.rect.bottom < viewport.y - 60 or widget.rect.y > viewport.bottom + 60:
                continue
            widget.draw(surface, fonts)

        self._draw_thinking(surface, fonts, viewport)

        surface.set_clip(previous_clip)
        self._draw_scrollbar(surface, viewport)

    def _draw_players(self, surface: pygame.Surface, fonts: FontBook) -> None:
        """双方信息（固定在头部，不参与滚动）。"""
        rect = self._players_rect
        if rect is None:
            return
        status = self.status
        for player in (0, 1):
            row = pygame.Rect(rect.x, rect.y + player * PLAYER_ROW_H, rect.width, PLAYER_ROW_H - 2)
            color = theme.PLAYER_COLORS[player]
            pygame.draw.circle(surface, color, (row.x + 8, row.centery), 6)
            if status.current_player == player and not status.is_over:
                pygame.draw.circle(surface, theme.lighten(color, 0.5), (row.x + 8, row.centery), 9, 2)
            render.text(surface, fonts.get(13), f"玩家 {player + 1}", (row.x + 22, row.centery),
                        theme.TEXT, baseline="middle")
            kind = status.player_types[player]
            # 详情（"墙 10" / "已落 12 子"）由窗口按当前棋类填；留空则回退到墙棋的表述
            detail = status.player_details[player] or f"墙 {status.walls_left[player]}"
            label = f"{PLAYER_TYPE_LABELS.get(kind, kind)} · {detail}"
            render.text(surface, fonts.get(12), label, (row.right, row.centery), theme.TEXT_DIM,
                        align="right", baseline="middle")

    def _draw_thinking(self, surface: pygame.Surface, fonts: FontBook, viewport: pygame.Rect) -> None:
        rect = self._thinking_rect
        if rect is None or not rect.colliderect(viewport):
            return
        status = self.status
        render.panel(surface, rect, color=theme.PANEL, radius=theme.RADIUS_SM, shadow=False)
        if status.is_thinking:
            dot_color = theme.mix(theme.TEXT_FAINT, theme.ACCENT, pulse(self._time))
            pygame.draw.circle(surface, dot_color, (rect.x + 14, rect.centery), 5)
            render.text(surface, fonts.get(12), f"AI 思考中 · {status.thinking_elapsed_ms:.0f} ms",
                        (rect.x + 26, rect.centery), theme.TEXT, baseline="middle")
        elif status.last_search:
            render.text(surface, fonts.get(12),
                        render.truncate(fonts.get(12), status.last_search, rect.width - 20),
                        (rect.x + 12, rect.centery), theme.TEXT_DIM, baseline="middle")
        else:
            render.text(surface, fonts.get(12), "AI 就绪", (rect.x + 12, rect.centery),
                        theme.TEXT_FAINT, baseline="middle")

    @staticmethod
    def _draw_arrow(surface: pygame.Surface, header: pygame.Rect, expanded: bool) -> None:
        """折叠箭头用绘制的三角形 —— 字形 ``▶`` 在部分中文字体里是缺字。"""
        cx, cy = header.x + 5, header.centery
        size = 4
        if expanded:
            points = [(cx - size, cy - size // 2), (cx + size, cy - size // 2), (cx, cy + size)]
        else:
            points = [(cx - size // 2, cy - size), (cx - size // 2, cy + size), (cx + size, cy)]
        pygame.draw.polygon(surface, theme.TEXT_FAINT, points)

    def _draw_scrollbar(self, surface: pygame.Surface, viewport: pygame.Rect) -> None:
        if self.max_scroll <= 1:
            return
        track = pygame.Rect(self.rect.right - 9, viewport.y + 6, 4, viewport.height - 12)
        render.rounded_rect(surface, track, theme.PANEL, theme.RADIUS_PILL)
        frac = viewport.height / (viewport.height + self.max_scroll)
        knob_h = max(30, int(track.height * frac))
        offset = (track.height - knob_h) * (self.scroll / self.max_scroll)
        knob = pygame.Rect(track.x, track.y + int(offset), track.width, knob_h)
        render.rounded_rect(surface, knob, theme.BORDER, theme.RADIUS_PILL)

    def _draw_footer(self, surface: pygame.Surface, fonts: FontBook) -> None:
        pygame.draw.line(
            surface, theme.BORDER_SOFT,
            (self.rect.x + 12, self.rect.bottom - FOOTER_H + 6),
            (self.rect.right - 12, self.rect.bottom - FOOTER_H + 6),
        )
        buttons = self._visible_footer()
        for i, button in enumerate(buttons):
            button.layout(self._footer_button_rect(i, len(buttons)))
            button.draw(surface, fonts)

    def _draw_dropdown_overlays(self, surface: pygame.Surface, fonts: FontBook) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        for dropdown in self._open_dropdowns():
            dropdown.draw_overlay(surface, fonts)
        surface.set_clip(previous_clip)
