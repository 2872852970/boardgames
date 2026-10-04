"""「设置」浮层：收纳**不常用 / 调一次就不再碰**的参数。

为什么拆出去
------------
侧栏是"边下边调"的地方，放的东西应该一眼能扫完；引擎参数（搜索深度、模拟次数）、
评估权重、动画时长这类"调一次就不再碰"的参数混在里面，只会把常用项挤进滚动区，
而且每次都要滚半天。所以侧栏只留**棋局设置 / 对局双方**，其余分组收进这个浮层
（侧栏底栏的「设置」按钮打开）。

按模式自动精简
--------------
和侧栏同一套可见性规则：``games=``（按棋类）、``needs_engine``（按**实际参战**的
引擎）逐项过滤 —— 双人对战里不会冒出一堆 AI 旋钮，人机 Minimax 里也不会
多出一整套 MCTS 参数。分组里一个控件都不剩时，整组不显示。

两列排布
--------
参数一共有二十来项，单列竖排必须滚很久才到底。这里把分组依次放进**两列**
（每次放进当前较矮的那一列，尽量平衡），一屏基本能看全，少滚几次也就少几次
鼠标操作。两列共用一个滚动条，整组的折叠 / 展开照旧。

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
from boardgames.ui.widgets import Button, Dropdown, Slider, Widget

#: 浮层卡片尺寸
CARD_W, CARD_MAX_H = 660, 640
CARD_PAD = 22
#: 两列之间的间距
COL_GAP = 20
ROW_GAP = 6
SCROLL_STEP = 48
#: 分组标题占的高度
ROW_H = 26
#: 列与列之间的竖向留白（每组结尾）
GROUP_GAP = 8
#: 标题栏里「全部恢复默认」按钮的宽度
RESET_ALL_W = 116


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
        #: 每组归属哪一列（0 / 1），在 :meth:`_layout_content` 里重算
        self._column_of: dict[str, int] = {}
        self.scroll = 0.0
        self.max_scroll = 0.0
        #: 正在接受键盘输入的数值框（同一时刻只允许一个）
        self._editing: Slider | None = None
        self._close_button = Button("×", self.close)
        #: 把当前**可见**（按棋类 / 引擎过滤后）的每一项都恢复成初始值
        self._reset_all = Button("全部恢复默认", self._reset_defaults, key="reset_all")
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
            widget = build_widget(spec, self.settings.get(spec.key), self.on_setting,
                                  self._begin_edit)
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
        self._end_editing(commit=True)

    # ------------------------------------------------------------------ #
    # 数值输入框（与侧栏同一套：点数值框直接键入）
    # ------------------------------------------------------------------ #

    def _begin_edit(self, widget: Slider) -> None:
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

    # ------------------------------------------------------------------ #
    # 恢复初始值
    # ------------------------------------------------------------------ #

    def _resettable_widgets(self) -> list[Widget]:
        """当前**看得见**（按棋类 / 引擎过滤后）且支持恢复初始值的控件。

        只重置看得见的那些：设置浮层里躺着 6 个棋类的权重，把别的棋类的值也
        一起刷成默认毫无意义，还可能顺手改动用户为别的棋类调好的参数。
        """
        return [
            widget
            for group in self._groups
            for widget in group.widgets
            if self._widget_applicable(widget)
            and getattr(widget, "supports_reset", False)
        ]

    def _refresh_reset_all(self) -> None:
        """一个都没改过时把「全部恢复默认」变灰：省得点了没反应让人以为坏了。"""
        self._reset_all.enabled = any(w.has_reset for w in self._resettable_widgets())

    def _reset_defaults(self) -> None:
        """「全部恢复默认」：把当前可见的每一项恢复成初始值。"""
        self._end_editing(commit=False)
        for widget in self._resettable_widgets():
            if widget.has_reset:
                widget.reset()
        # 立刻刷新按钮状态，而不是等下一帧 update —— 点完还是亮的会让人以为没生效
        self._refresh_reset_all()

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

    def _content_clip(self) -> pygame.Rect:
        """内容可见区（标题栏以下、卡片以内）—— 绘制与点击判定共用。"""
        clip = self._card.inflate(-8, -8)
        clip.top = self._card.y + 58
        return clip

    def _column_rect(self, index: int) -> pygame.Rect:
        """第 ``index`` 列的内容矩形（宽度已扣掉内边距与列间距）。"""
        width = (self._card.width - CARD_PAD * 2 - COL_GAP) // 2
        x = self._card.x + CARD_PAD + index * (width + COL_GAP)
        return pygame.Rect(x, 0, width, 0)

    def _section_widgets(self, widgets: list[Widget]) -> list[Widget]:
        return [w for w in widgets if self._widget_applicable(w)]

    def _group_height(self, group: _Group) -> int:
        rows = self._section_widgets(group.widgets)
        if not rows:
            return 0
        total = ROW_H + GROUP_GAP
        if group.expanded:
            total += sum(widget.height + ROW_GAP for widget in rows)
        return total

    def _content_height(self) -> int:
        """两列中最高的那一列的高度。"""
        heights = [0, 0]
        for group in self._groups:
            if not self._section_widgets(group.widgets):
                continue
            index = self._column_of.get(group.group_id, 0)
            heights[index] += self._group_height(group)
        return max(heights)

    def _assign_columns(self) -> None:
        """把分组依次放进"当前较矮"的那一列（贪心，尽量平衡两列高度）。"""
        heights = [0, 0]
        self._column_of = {}
        for group in self._groups:
            if not self._section_widgets(group.widgets):
                continue
            index = 0 if heights[0] <= heights[1] else 1
            self._column_of[group.group_id] = index
            heights[index] += self._group_height(group)

    def _fit_card(self) -> None:
        """卡片尺寸**恒定**，内容交给滚动条。

        以前这里是"高度跟着内容走"（整组收起卡片就跟着缩）。那个做法在观感上
        很糟：折叠一个分组，卡片、关闭按钮、两列的位置全都会跳一下，而用户
        想要的只是"少看几行"。所以现在高度只由可用区域决定，折叠 / 展开只改变
        `max_scroll`（内容超了就滚动），卡片一帧都不动。
        """
        height = max(260, min(CARD_MAX_H, self._area.height - 48))
        self._card = pygame.Rect(0, 0, CARD_W, height)
        self._card.center = self._area.center
        self._close_button.layout(
            pygame.Rect(self._card.right - 40, self._card.y + 10, 30, 30)
        )
        self._reset_all.layout(
            pygame.Rect(self._card.right - 40 - 8 - RESET_ALL_W, self._card.y + 10,
                        RESET_ALL_W, 30)
        )

    def _open_dropdowns(self) -> list[Dropdown]:
        return [w for w in self._visible_widgets() if isinstance(w, Dropdown) and w.open]

    def _layout_content(self) -> None:
        # 先定两列归属与卡片高度，再往里排控件
        self._assign_columns()
        self._fit_card()
        top = self._content_top() - int(self.scroll)
        self._headers.clear()
        # 每列自己往下排
        pen = [top, top]
        for group in self._groups:
            rows = self._section_widgets(group.widgets)
            if not rows:
                for widget in group.widgets:
                    widget.visible = False
                    widget.layout(pygame.Rect(0, -9000, 0, 0))
                continue
            column = self._column_of.get(group.group_id, 0)
            rect = self._column_rect(column)
            y = pen[column]
            self._headers.append((group, pygame.Rect(rect.x, y, rect.width, ROW_H)))
            y += ROW_H
            if group.expanded:
                for widget in rows:
                    widget.visible = True
                    widget.layout(pygame.Rect(rect.x, y, rect.width, widget.height))
                    y += widget.height + ROW_GAP
            else:
                # 收起时把控件挪出画面：它们既不该接事件，也不该被点到
                for widget in rows:
                    widget.visible = False
                    widget.layout(pygame.Rect(0, -9000, 0, 0))
            pen[column] = y + GROUP_GAP
        # 不适用的控件一律不可见（它们可能上一轮还在画面里）
        for group in self._groups:
            for widget in group.widgets:
                if not self._widget_applicable(widget):
                    widget.visible = False
        tallest = max(pen) - top
        self.max_scroll = max(0.0, tallest + 8 - (self._card.height - 64 - CARD_PAD))
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """开着时是**模态**的：吃掉全部事件并返回 ``True``。"""
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN:
            # 正在输入数值：键盘先给它（否则 Esc 会把整个浮层关掉、数字根本打不进去）
            if self._editing is not None:
                self._editing.handle_key(event)
                if not self._editing.editing:
                    self._editing = None
                return True
            if event.key in (pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                self.close()
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0.0, min(self.max_scroll, self.scroll - event.y * SCROLL_STEP))
            self._layout_content()
            return True
        if self._close_button.handle_event(event):
            return True
        if self._reset_all.handle_event(event):
            return True
        # ---- 点别处就确认并结束输入 ----
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
        # 一个都没改过的时候按钮变灰：省得点了没反应让人以为坏了
        self._refresh_reset_all()
        self._reset_all.update(dt_ms, mouse)
        # 正在编辑的输入框被折叠 / 过滤掉时，直接确认收工
        if self._editing is not None and (
            not self._editing.visible or not self._editing.enabled
        ):
            self._end_editing(commit=True)
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
                    (self._card.x + CARD_PAD, self._card.y + 18), theme.TEXT)
        render.text(surface, fonts.get(12), "改动立即生效并自动保存 · 只列出这一局用得上的参数",
                    (self._card.x + CARD_PAD, self._card.y + 42), theme.TEXT_FAINT)
        self._reset_all.draw(surface, fonts)
        self._close_button.draw(surface, fonts)
        pygame.draw.line(surface, theme.BORDER_SOFT,
                         (self._card.x + 14, self._card.y + 52),
                         (self._card.right - 14, self._card.y + 52))
        # 两列之间的分隔线
        columns = self._column_rect(0)
        if columns.width > 0:
            gap_x = columns.right + COL_GAP // 2
            clip = self._content_clip()
            pygame.draw.line(surface, theme.BORDER_SOFT, (gap_x, clip.y + 4),
                             (gap_x, clip.bottom - 4))

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
        # 展开的下拉列表必须画在其它控件之上（当前分组里只有开关 / 滑块，留个兜底）
        for dropdown in self._open_dropdowns():
            dropdown.draw_overlay(surface, fonts)
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
