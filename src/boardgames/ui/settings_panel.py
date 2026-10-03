"""「设置」浮层：收纳**不常用**的参数（评估权重、界面与操作）。

为什么拆出去
------------
侧栏是"边下边调"的地方，放的东西应该一眼能扫完；评估权重、动画时长这类
"调一次就不再碰"的参数混在里面只会把常用项挤下滚动区。所以侧栏只留
**棋局设置 / 对局双方 / 引擎参数**，其余分组收进这个浮层（侧栏底栏的
「设置」按钮打开）。

结构上它是一个**模态**浮层：开着时吃掉全部事件（棋盘 / 侧栏不再响应），
``Esc`` / 点遮罩 / 点 ``×`` 都能关。控件本体与侧栏共用同一套
:func:`boardgames.ui.sidebar.build_widget` 工厂，值照样直接写回
:class:`~boardgames.settings.Settings` 并持久化。

分组标题**可折叠**（与侧栏一致：点标题行收起 / 展开，箭头用
:func:`~boardgames.ui.render.disclosure_arrow` 画）。折叠状态只在本局内记住 ——
它是"这一刻想不想看"的事，不值得占用设置项。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from boardgames.settings import GROUPS, SPEC_BY_KEY, SPECS, Settings
from boardgames.ui import render, theme
from boardgames.ui.fonts import FontBook
from boardgames.ui.sidebar import PANEL_GROUPS, build_widget
from boardgames.ui.widgets import Button, Widget

#: 浮层卡片尺寸
CARD_W, CARD_MAX_H = 520, 620
CARD_PAD = 22
ROW_GAP = 6
SCROLL_STEP = 48
#: 分组标题占的高度
ROW_H = 26


@dataclass
class _Group:
    """浮层里的一组参数；点标题行折叠 / 展开。"""

    group_id: str
    title: str
    widgets: list[Widget] = field(default_factory=list)
    #: 默认**展开**：点开「设置」就是为了改它们，藏着只会让人以为没这一项
    expanded: bool = True


class SettingsPanel:
    """模态参数浮层。由 :class:`~boardgames.ui.match_scene.MatchScene` 持有。"""

    def __init__(self, settings: Settings, on_setting) -> None:
        self.settings = settings
        self.on_setting = on_setting
        self.open = False
        self.game_key = ""
        self._player_types: tuple[str, str] = ("human", "human")
        self._area = pygame.Rect(0, 0, theme.WINDOW_W, theme.WINDOW_H)
        self._card = pygame.Rect(0, 0, CARD_W, 500)
        self._groups: list[_Group] = []
        self._headers: list[tuple[_Group, pygame.Rect]] = []
        self.scroll = 0.0
        self.max_scroll = 0.0
        self._close_button = Button("×", self.close)
        self._build()

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def group(self, group_id: str) -> _Group:
        for group in self._groups:
            if group.group_id == group_id:
                return group
        raise KeyError(group_id)

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        by_group: dict[str, list[Widget]] = {gid: [] for gid, _ in GROUPS}
        for spec in SPECS:
            if not spec.expose or spec.group not in PANEL_GROUPS:
                continue
            widget = build_widget(spec, self.settings.get(spec.key), self.on_setting)
            if widget is not None:
                by_group[spec.group].append(widget)
        self._groups = [
            _Group(gid, title, by_group[gid])
            for gid, title in GROUPS
            if gid in PANEL_GROUPS and by_group[gid]
        ]

    def _widget_applicable(self, widget: Widget) -> bool:
        spec = SPEC_BY_KEY.get(widget.key)
        if spec is None:
            return True
        if spec.games and self.game_key not in spec.games:
            return False
        kinds = {kind for kind in self._player_types if kind != "human"}
        if spec.needs_engine:
            return spec.needs_engine in kinds
        if spec.needs_ai:
            return bool(kinds)
        return True

    def _visible_widgets(self) -> list[Widget]:
        """当前会画出来、也能接事件的控件（**折叠的分组整组不算**）。"""
        return [
            widget
            for group in self._groups
            if group.expanded
            for widget in group.widgets
            if self._widget_applicable(widget)
        ]

    # ------------------------------------------------------------------ #
    # 打开 / 关闭
    # ------------------------------------------------------------------ #

    def show(self, game_key: str, player_types: tuple[str, str]) -> None:
        self.game_key = game_key
        self._player_types = player_types
        self.open = True
        self.scroll = 0.0
        self.sync_from_settings()
        # 按新棋类过滤后必须重排 —— 否则不适用 / 新出现的控件还停在上一轮的坐标上
        self._layout_content()

    def close(self) -> None:
        self.open = False

    def _all_widgets(self) -> list[Widget]:
        return [widget for group in self._groups for widget in group.widgets]

    def sync_from_settings(self) -> None:
        # 同步**全部**控件而不只是可见的：折叠中的分组稍后展开时要显示当前值，
        # 不能还停在"上一次打开时"的旧值上。
        for widget in self._all_widgets():
            widget.set_value_silently(self.settings.get(widget.key))

    # ------------------------------------------------------------------ #
    # 布局 / 事件 / 绘制
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self._area = pygame.Rect(area)
        self._layout_content()

    def _content_top(self) -> int:
        return self._card.y + 64

    def _content_height(self) -> int:
        """当前内容的总高度（标题栏以下的部分）。"""
        total = 0
        for group in self._groups:
            rows = self._section_widgets(group.widgets)
            if not rows:
                continue
            total += ROW_H
            if group.expanded:
                for widget in rows:
                    total += widget.height + ROW_GAP
            total += 6
        return total

    def _fit_card(self) -> None:
        """卡片高度跟着内容走（上限 :data:`CARD_MAX_H`）。

        把整组收起来之后卡片必须跟着缩 —— 不然「设置」底下会留一大片空白，
        看着像内容加载失败了。
        """
        needed = 64 + self._content_height() + CARD_PAD + 8
        height = max(240, min(CARD_MAX_H, self._area.height - 48, needed))
        self._card = pygame.Rect(0, 0, CARD_W, height)
        self._card.center = self._area.center
        self._close_button.layout(
            pygame.Rect(self._card.right - 40, self._card.y + 10, 30, 30)
        )

    def _section_widgets(self, widgets: list[Widget]) -> list[Widget]:
        return [w for w in widgets if self._widget_applicable(w)]

    def _content_clip(self) -> pygame.Rect:
        """内容可见区（标题栏以下、卡片以内）—— 绘制与点击判定共用。"""
        clip = self._card.inflate(-8, -8)
        clip.top = self._card.y + 58
        return clip

    def _layout_content(self) -> None:
        # 先定卡片高度（它只依赖"哪些组展开着"），再往里排控件
        self._fit_card()
        y = self._content_top() - int(self.scroll)
        top = y
        content_w = self._card.width - CARD_PAD * 2
        x = self._card.x + CARD_PAD
        self._headers.clear()
        for group in self._groups:
            rows = self._section_widgets(group.widgets)
            if not rows:
                continue
            self._headers.append((group, pygame.Rect(x, y, content_w, 26)))
            y += ROW_H
            if group.expanded:
                for widget in rows:
                    widget.visible = True
                    widget.layout(pygame.Rect(x, y, content_w, widget.height))
                    y += widget.height + ROW_GAP
            else:
                # 收起时把控件挪出画面：它们既不该接事件，也不该被点到
                for widget in rows:
                    widget.visible = False
                    widget.layout(pygame.Rect(0, -9000, 0, 0))
            y += 6
        for group in self._groups:
            for widget in group.widgets:
                if not self._widget_applicable(widget):
                    widget.visible = False
        self.max_scroll = max(0.0, (y - top) + 8 - (self._card.height - 64 - CARD_PAD))
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """开着时是**模态**的：吃掉全部事件并返回 ``True``。"""
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN,
        ):
            self.close()
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0.0, min(self.max_scroll, self.scroll - event.y * SCROLL_STEP))
            self._layout_content()
            return True
        if self._close_button.handle_event(event):
            return True
        # ---- 分组标题：左键按下才折叠 / 展开（不判类型的话鼠标划过就每帧翻转） ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clip = self._content_clip()
            for group, header in self._headers:
                if header.collidepoint(event.pos) and clip.collidepoint(event.pos):
                    group.expanded = not group.expanded
                    self._layout_content()
                    return True
        for widget in reversed(self._visible_widgets()):
            if widget.handle_event(event):
                return True
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and not self._card.collidepoint(event.pos)
        ):
            self.close()
        return True

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        if not self.open:
            return
        self._close_button.update(dt_ms, mouse)
        for widget in self._visible_widgets():
            widget.update(dt_ms, mouse if self._card.collidepoint(mouse) else (-1, -1))

    def draw(self, surface, fonts: FontBook) -> None:
        if not self.open:
            return
        veil = pygame.Surface(self._area.size, pygame.SRCALPHA)
        veil.fill((*theme.BG, 170))
        surface.blit(veil, self._area.topleft)

        render.panel(surface, self._card, color=theme.PANEL, radius=theme.RADIUS + 4)
        render.text(surface, fonts.get(18, bold=True), "设置",
                    (self._card.x + CARD_PAD, self._card.y + 20), theme.TEXT)
        render.text(surface, fonts.get(12), "改动立即生效并自动保存",
                    (self._card.x + CARD_PAD, self._card.y + 42), theme.TEXT_FAINT)
        self._close_button.draw(surface, fonts)
        pygame.draw.line(surface, theme.BORDER_SOFT,
                         (self._card.x + 14, self._card.y + 52),
                         (self._card.right - 14, self._card.y + 52))

        previous_clip = surface.get_clip()
        clip = self._content_clip()
        surface.set_clip(clip)
        for group, header in self._headers:
            if not header.colliderect(clip):
                continue
            render.disclosure_arrow(
                surface, (header.x + 4, header.centery), group.expanded,
                theme.TEXT_DIM if group.expanded else theme.TEXT_FAINT,
            )
            bold = fonts.get(13, bold=True)
            render.text(surface, bold, group.title, (header.x + 14, header.centery),
                        theme.TEXT if group.expanded else theme.TEXT_DIM, baseline="middle")
            line_x = header.x + 22 + bold.size(group.title)[0]
            if line_x < header.right:
                pygame.draw.line(surface, theme.BORDER_SOFT, (line_x, header.centery),
                                 (header.right, header.centery), 1)
            if not group.expanded:
                render.text(surface, fonts.get(11), f"{len(self._section_widgets(group.widgets))} 项已收起",
                            (header.right - 2, header.centery), theme.TEXT_FAINT,
                            align="right", baseline="middle")
        for widget in self._visible_widgets():
            if widget.rect.bottom < clip.top or widget.rect.y > clip.bottom:
                continue
            widget.draw(surface, fonts)
        surface.set_clip(previous_clip)

        # 滚动条（内容超出卡片时）
        if self.max_scroll > 1:
            track = pygame.Rect(self._card.right - 8, clip.y + 4, 4, clip.height - 8)
            render.rounded_rect(surface, track, theme.PANEL_HOVER, theme.RADIUS_PILL)
            frac = clip.height / (clip.height + self.max_scroll)
            knob_h = max(30, int(track.height * frac))
            offset = (track.height - knob_h) * (self.scroll / self.max_scroll)
            knob = pygame.Rect(track.x, track.y + int(offset), track.width, knob_h)
            render.rounded_rect(surface, knob, theme.BORDER, theme.RADIUS_PILL)
