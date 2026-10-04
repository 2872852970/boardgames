"""游戏选择大厅：卡片网格 + 玩法简介 + 规则说明。

卡片数据全部来自 :class:`~boardgames.core.game.Game` 上的元数据 ClassVar
（``tagline`` / ``summary`` / ``rules`` / ``howto`` / ``tips`` / ``icon``），由
:meth:`~boardgames.core.registry.GameRegistry.all_games` 遍历生成 ——
**以后再接第五个棋类，大厅这边零改动。**

卡片上只放三行文字
------------------
图标 + 名称 + 副标题 + 一行简介就够认了。完整的规则（``rules``）挪进了
「规则说明」浮层（:class:`~boardgames.ui.rules_panel.RulesOverlay`）——
卡片塞不下，而写不全的规则等于没规则。

图标是"情境切片"
----------------
每个图标画的是**一局棋里的一个瞬间**，而不是抽象的棋盘网格：谁在推谁、
墙挡在哪、哪条线快连成了、蜂后还差几面被围满。这样一眼能看出"这个棋在玩什么"，
而不是"它长什么样"。

交互
----
* 鼠标移到卡片上高亮，点击卡片进入对局；点卡片底部的「规则说明」打开规则浮层；
* 键盘 ``←/→`` 行内移动、``↑/↓`` 跨行、``Enter/Space`` 进入、``R`` 看规则、``Esc`` 退出程序；
* 小屏（``choose_window_size`` 裁剪后可能只剩 760×560）单列放不下时启用滚轮。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

from boardgames.ui import render, theme
from boardgames.ui.fonts import FontBook
from boardgames.ui.rules_panel import RulesOverlay
from boardgames.ui.widgets import Button

if TYPE_CHECKING:  # 避免运行时循环 import
    from boardgames.core.game import Game
    from boardgames.ui.window import GameWindow

#: 卡片网格的排布断点（按可用宽度）
COLS_NARROW, COLS_MEDIUM = 760, 1080
#: 卡片尺寸上下限
CARD_MIN_W, CARD_MAX_W = 232, 320
CARD_MIN_H, CARD_MAX_H = 236, 300
CARD_GAP = 22
#: 标题区高度（从顶部留白到第一行卡片）
HEADER_SPACE = 108
#: 底部提示区
FOOTER_SPACE = 62
#: 卡片里示意图标区的高度
ICON_H = 96
#: 卡片底部「规则说明」按钮
RULES_BTN_H = 30


@dataclass
class _Card:
    game: Game
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    rules_rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


class LobbyScene:
    """游戏选择大厅。"""

    def __init__(self, window: GameWindow) -> None:
        self.window = window
        self.area = pygame.Rect(0, 0, theme.WINDOW_W, theme.WINDOW_H)
        self.scroll = 0.0
        self.max_scroll = 0.0
        self._hover = -1
        self._focus = 0
        self._time = 0.0
        # 卡片只认 Game 的**只读**元数据。注意 all_games() 返回的是注册表里
        # 的共享单例，绝不能在这里调 initial_state() 之类有副作用的方法。
        self._cards = [_Card(game) for game in window.registry.all_games()]
        self._rules_buttons = [
            Button("规则说明", lambda i=i: self._open_rules(i))
            for i in range(len(self._cards))
        ]
        self.rules = RulesOverlay()

    # ------------------------------------------------------------------ #
    # 场景接口
    # ------------------------------------------------------------------ #

    def on_enter(self) -> None:
        self._focus = 0
        self._hover = -1
        self.scroll = 0.0

    def on_exit(self) -> None:
        self.rules.close()

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self.rules.layout(area)
        count = len(self._cards)
        if not count:
            return
        width = area.width
        if width < COLS_NARROW:
            cols = 1
        elif width < COLS_MEDIUM:
            cols = 2
        else:
            cols = min(3, count)
        rows = math.ceil(count / cols)

        card_w = int(min(CARD_MAX_W, (width - 80 - CARD_GAP * (cols - 1)) / cols))
        card_h = int(min(CARD_MAX_H, (area.height - HEADER_SPACE - FOOTER_SPACE
                                       - CARD_GAP * (rows - 1)) / rows))
        card_w = max(CARD_MIN_W, card_w)
        card_h = max(CARD_MIN_H, card_h)

        grid_w = card_w * cols + CARD_GAP * (cols - 1)
        grid_h = card_h * rows + CARD_GAP * (rows - 1)
        left = area.x + (area.width - grid_w) // 2
        # 网格整体在"标题区下方 ~ 底部提示区上方"之间垂直居中
        available_h = area.height - HEADER_SPACE - FOOTER_SPACE
        top = area.y + HEADER_SPACE + max(0, (available_h - grid_h) // 2)

        pad = theme.PADDING
        for i, card in enumerate(self._cards):
            card.rect = pygame.Rect(
                left + (i % cols) * (card_w + CARD_GAP),
                top + (i // cols) * (card_h + CARD_GAP) - int(self.scroll),
                card_w, card_h,
            )
            bottom = card.rect.bottom - pad
            card.rules_rect = pygame.Rect(
                card.rect.x + pad, bottom - RULES_BTN_H,
                card.rect.width - pad * 2, RULES_BTN_H,
            )
            self._rules_buttons[i].layout(card.rules_rect)
        # 放不下时允许滚动（否则底部一排会画到屏幕外）
        viewport_bottom = area.bottom - FOOTER_SPACE
        self.max_scroll = max(0.0, top + grid_h - viewport_bottom)
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def handle_event(self, event: pygame.event.Event) -> bool:
        # 规则浮层开着时它是**模态**的：吃掉全部事件，底下的卡片不再响应
        if self.rules.open:
            self.rules.handle_event(event)
            return True

        # 卡片上的「规则说明」按钮比卡片本身优先（否则点它就等于进对局了）
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            for button in self._rules_buttons:
                if button.handle_event(event):
                    return True

        if event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y * 48)
            return True

        if event.type == pygame.MOUSEMOTION:
            self._hover = self._index_at(event.pos)
            if self._hover >= 0:
                self._focus = self._hover
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            index = self._index_at(event.pos)
            if index >= 0:
                self._enter(index)
            return True

        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)
        return False

    def _handle_key(self, event: pygame.event.Event) -> bool:
        count = len(self._cards)
        if not count:
            return event.key == pygame.K_ESCAPE
        if event.key == pygame.K_ESCAPE:
            self.window.running = False
        elif event.key in (pygame.K_LEFT, pygame.K_UP):
            self._focus = (self._focus - 1) % count
            self._ensure_visible()
        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
            self._focus = (self._focus + 1) % count
            self._ensure_visible()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._enter(self._focus)
        elif event.key in (pygame.K_r, pygame.K_h, pygame.K_SLASH):
            # R = 规则（Rules）；H / ? 也认，反正这里没有别的冲突
            self._open_rules(self._focus)
        return True

    def _index_at(self, pos: tuple[int, int]) -> int:
        for i, card in enumerate(self._cards):
            if card.rect.collidepoint(pos):
                return i
        return -1

    def _scroll_by(self, delta: float) -> None:
        self.scroll = max(0.0, min(self.max_scroll, self.scroll + delta))
        self.layout(self.area)

    def _ensure_visible(self) -> None:
        card = self._cards[self._focus]
        viewport_top = self.area.y + HEADER_SPACE
        viewport_bottom = self.area.bottom - FOOTER_SPACE
        if card.rect.top < viewport_top:
            self.scroll -= viewport_top - card.rect.top
        elif card.rect.bottom > viewport_bottom:
            self.scroll += card.rect.bottom - viewport_bottom
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))
        self.layout(self.area)

    def _enter(self, index: int) -> None:
        if 0 <= index < len(self._cards):
            self.window.goto_match(self._cards[index].game.key)

    def _open_rules(self, index: int) -> None:
        if 0 <= index < len(self._cards):
            self.rules.show(self._cards[index].game)

    # ------------------------------------------------------------------ #
    # 更新与绘制
    # ------------------------------------------------------------------ #

    def update(self, dt_ms: float) -> None:
        self._time += dt_ms / 1000.0
        mouse = pygame.mouse.get_pos()
        for button in self._rules_buttons:
            button.update(dt_ms, mouse)
        self.rules.update(dt_ms, mouse)

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        surface.fill(theme.BG)
        self._draw_header(surface, fonts)
        # 底部提示先画：它是固定不动的，卡片滚动时从它上面经过才符合"在下方"的层次
        self._draw_footer_hint(surface, fonts)
        for i, card in enumerate(self._cards):
            # 滚出视野的卡片不必画
            if card.rect.bottom < self.area.y - 40 or card.rect.top > self.area.bottom + 40:
                continue
            self._draw_card(surface, fonts, i, card)
            self._rules_buttons[i].draw(surface, fonts)
        self._draw_scrollbar(surface)
        self.rules.draw(surface, fonts)

    def _draw_header(self, surface, fonts: FontBook) -> None:
        render.text(surface, fonts.get(30, bold=True), "选个游戏",
                    (self.area.centerx, self.area.y + 34), theme.TEXT,
                    align="center", baseline="middle")
        render.text(surface, fonts.get(14), "双人对战 · 人机对战 · AI 自对弈，侧栏可实时调参",
                    (self.area.centerx, self.area.y + 66), theme.TEXT_FAINT,
                    align="center", baseline="middle")

    def _draw_card(self, surface, fonts: FontBook, index: int, card: _Card) -> None:
        game = card.game
        hovered = index == self._hover
        focused = index == self._focus
        # 焦点卡的边框随时间轻微呼吸，让"当前选中"始终看得出来
        breathe = 0.5 + 0.5 * abs((self._time * 1.6) % 2.0 - 1.0)
        fill = theme.PANEL_HOVER if hovered else theme.PANEL

        render.soft_shadow(surface, card.rect, theme.RADIUS + 2, spread=3)
        render.rounded_rect(surface, card.rect, fill, theme.RADIUS + 2)
        border = theme.ACCENT_HOVER if hovered else theme.BORDER_SOFT
        if focused:
            border = theme.mix(theme.ACCENT, theme.ACCENT_HOVER, breathe)
        render.rounded_rect(surface, card.rect, border, theme.RADIUS + 2, width=2 if focused else 1)

        pad = theme.PADDING
        inner = card.rect.inflate(-pad * 2, -pad * 2)
        body = fonts.get(12)
        bold = fonts.get(19, bold=True)

        # 正文只有三行，图标区吃掉剩下的高度；内容比空间短时整块垂直居中
        content_h = ICON_H + 8 + 26 + 20 + 18
        avail = inner.height - RULES_BTN_H - 10
        top = inner.y + max(0, (avail - content_h) // 2)
        y = top

        icon_rect = pygame.Rect(inner.x, y, inner.width, ICON_H)
        self._draw_icon(surface, icon_rect, game.icon)
        y = icon_rect.bottom + 8

        render.text(surface, bold, game.display_name, (inner.x, y), theme.TEXT, baseline="middle")
        y += 26
        render.text(surface, fonts.get(12), game.tagline or game.key,
                    (inner.x, y), theme.TEXT_FAINT, baseline="middle")
        y += 20
        # 简介只给一行：完整的规则在「规则说明」里，卡片上塞不下也不需要
        render.text(surface, body, render.truncate(body, getattr(game, "summary", ""), inner.width),
                    (inner.x, y), theme.TEXT_DIM, baseline="middle")

    def _draw_footer_hint(self, surface, fonts: FontBook) -> None:
        if not self._cards:
            render.text(surface, fonts.get(15), "还没有注册任何游戏",
                        (self.area.centerx, self.area.centery), theme.TEXT_FAINT,
                        align="center", baseline="middle")
            return
        render.text(
            surface, fonts.get(12),
            "点击卡片进入对局 · 「规则说明」看完整规则 · ←↑↓→ 选择 · Enter 进入 · R 规则 · Esc 退出",
            (self.area.centerx, self.area.bottom - 30), theme.TEXT_FAINT,
            align="center", baseline="middle",
        )

    def _draw_scrollbar(self, surface) -> None:
        if self.max_scroll <= 1:
            return
        track = pygame.Rect(
            self.area.right - 14, self.area.y + HEADER_SPACE, 4,
            self.area.height - HEADER_SPACE - FOOTER_SPACE,
        )
        render.rounded_rect(surface, track, theme.PANEL, theme.RADIUS_PILL)
        frac = track.height / (track.height + self.max_scroll)
        knob_h = max(30, int(track.height * frac))
        offset = (track.height - knob_h) * (self.scroll / self.max_scroll)
        render.rounded_rect(
            surface,
            pygame.Rect(track.x, track.y + int(offset), track.width, knob_h),
            theme.BORDER, theme.RADIUS_PILL,
        )

    # ------------------------------------------------------------------ #
    # 卡片图标：一局棋里的一个瞬间（纯 pygame.draw，**不用文字 / emoji**）
    # ------------------------------------------------------------------ #

    def _draw_icon(self, surface, rect: pygame.Rect, kind: str) -> None:
        if kind == "drop":
            self._icon_connect4(surface, rect)
        elif kind == "board":
            self._icon_quoridor(surface, rect)
        elif kind == "hex":
            self._icon_abalone(surface, rect)
        elif kind == "hive":
            self._icon_hive(surface, rect)
        elif kind == "dotsboxes":
            self._icon_dotsboxes(surface, rect)
        elif kind == "mancala":
            self._icon_mancala(surface, rect)
        else:
            self._icon_dots(surface, rect)

    def _icon_quoridor(self, surface, rect: pygame.Rect) -> None:
        """步步为营：己子被一面墙挡住，只能绕路 —— 墙棋的全部乐趣就在这一下。

        上下两条底线是双方各自的目标，墙横在 P0 的正前方。
        """
        cols, rows, pitch, cell = 5, 5, 17, 13
        cx, cy = rect.centerx, rect.centery
        left = cx - (cols - 1) * pitch / 2
        top = cy - (rows - 1) * pitch / 2

        def at(col: float, row: float) -> tuple[float, float]:
            return (left + col * pitch, top + row * pitch)

        # 双方的目标底线（上=玩家 1 的目标，下=玩家 2 的目标）
        for player, row in ((0, -1), (1, rows)):
            y = top + (row + 0.26) * pitch
            pygame.draw.line(surface, theme.PLAYER_DARK[player],
                             (left - 7, y), (left + (cols - 1) * pitch + 7, y), 2)

        for r in range(rows):
            for c in range(cols):
                x, y = at(c, r)
                render.rounded_rect(
                    surface, pygame.Rect(x - cell / 2, y - cell / 2, cell, cell),
                    theme.CELL_ALT, 3,
                )

        # 墙：横在 P0 正前方（第 2、3 行之间，跨第 1~2 列），把它去路堵上
        wx = at(1, 0)[0] - pitch / 2
        wy = (at(0, 2)[1] + at(0, 3)[1]) / 2 - 3
        wall = pygame.Rect(wx, wy, pitch * 2, 7)
        render.rounded_rect(surface, wall.move(0, 2), theme.WALL_SHADOW, 3)
        render.rounded_rect(surface, wall, theme.WALL, 3)
        render.rounded_rect(surface, pygame.Rect(wall.x + 2, wall.y + 1, wall.width - 4, 2),
                            theme.WALL_EDGE, 2)

        # 绕行：走"直来直去"的直角折线 —— 上一格 → 左两格 → 再往上，
        # 拐弯处不画圆角，免得看上去像条随手画的曲线
        x0, _ = at(0, 0)
        x2, _ = at(2, 0)
        _, y1 = at(0, 1)
        _, y3 = at(0, 3)
        _, y4 = at(0, 4)
        turn_y = y3 + 6  # 贴着墙的下沿走
        path = [
            (x2, y4 - 9), (x2, turn_y), (x0, turn_y), (x0, y1 - 2),
        ]
        _dashed(surface, path, theme.ACCENT, 2)
        _arrow(surface, (x0, y1 - 2), -math.pi / 2, theme.ACCENT, 6)

        # 两枚棋子：P0 在下方（往上走），P1 在上方
        _marble(surface, at(2, rows - 1), 6, 0)
        _marble(surface, at(2, 0), 6, 1)

    def _icon_connect4(self, surface, rect: pygame.Rect) -> None:
        """重力四子棋：底行已经三连，第四格空着 —— 落进去就赢。

        落点不画"悬在棋盘上方的一枚子"（那样太突兀，也不像真实盘面），
        而是像游戏里那样把**落点预览**画在格子里：一个虚线圆环。
        重力则交给最左那一列的堆叠来表达。
        """
        cols, rows, pitch, hole = 5, 4, 22, 9
        cx, cy = rect.centerx, rect.centery
        left = cx - (cols - 1) * pitch / 2
        top = cy - (rows - 1) * pitch / 2
        plate = pygame.Rect(left - pitch / 2, top - pitch / 2,
                            (cols - 1) * pitch + pitch, (rows - 1) * pitch + pitch)
        render.rounded_rect(surface, plate, theme.BG_ALT, theme.RADIUS_SM)
        render.rounded_rect(surface, plate, theme.BORDER_SOFT, theme.RADIUS_SM, 1)
        for r in range(rows):
            for c in range(cols):
                pygame.draw.circle(surface, theme.BG, (left + c * pitch, top + r * pitch), hole)

        def slot(col: int, row: int) -> tuple[float, float]:
            return (left + col * pitch, top + row * pitch)

        # 对手两枚叠在最左一列 —— 一眼看出"棋子是从上面掉下来的"
        _marble(surface, slot(0, rows - 1), hole - 1, 1)
        _marble(surface, slot(0, rows - 2), hole - 1, 1)
        # 玩家 1 的底行三连
        for c in (1, 2, 3):
            _marble(surface, slot(c, rows - 1), hole - 1, 0)

        # 四连线：底行第 1~4 格，最后一格还空着
        line_y = slot(0, rows - 1)[1]
        _dashed(surface, [(left + pitch * 0.5, line_y), (left + pitch * 4.5, line_y)],
                theme.P0_DARK, 2)
        # 空着的那一格 = 落点预览（虚线圆环 + 中心一个点），和游戏里的 hover 预览同一套语汇
        tx, ty = slot(4, rows - 1)
        ring = [
            (tx + (hole - 2) * math.cos(i * math.pi / 9),
             ty + (hole - 2) * math.sin(i * math.pi / 9))
            for i in range(19)
        ]
        _dashed(surface, ring, theme.P0, 2, dash=3, gap=3)
        pygame.draw.circle(surface, theme.P0, (int(tx), int(ty)), 2)

    def _icon_abalone(self, surface, rect: pygame.Rect) -> None:
        """大力士棋：一盘残局 —— 盘上双方都还剩一批子，盘外已经躺着出局的。

        中央那一手是重点：三枚己方子把一枚对方子顶向盘外，箭头指着虚线边界。
        """
        cx, cy = rect.centerx, rect.centery
        gap, radius = 17.0, 5.4
        r0 = int(radius)
        # 只画到离心度 2 —— 再往外卡片上就挤不下了，但"六边形点阵"已经够认
        for q in range(-2, 3):
            for r in range(-2, 3):
                if max(abs(q), abs(r), abs(q + r)) > 2:
                    continue
                pos = (cx + gap * (q + r / 2.0), cy + gap * 0.87 * r)
                pygame.draw.circle(surface, theme.CELL_ALT, pos, radius)

        def at(q: float, r: float = 0.0) -> tuple[float, float]:
            return (cx + gap * (q + r / 2.0), cy + gap * 0.87 * r)

        # 盘上：双方各留一批子（残局），不是光秃秃的四个
        for q, r in ((-2, 0), (-1, 0), (0, 0), (-2, 1), (-1, -1), (0, -2)):
            _marble(surface, at(q, r), r0, 0)
        for q, r in ((1, 0), (0, 2), (2, -2), (1, 1)):
            _marble(surface, at(q, r), r0, 1)

        # 盘外边界（左右各一条虚线）+ 已经被挤出去的子 —— "挤出 6 子"的进度感
        dy = gap * 1.35
        for edge in (cx - gap * 2.62, cx + gap * 2.62):
            _dashed(surface, [(edge, cy - dy), (edge, cy + dy)],
                    theme.TEXT_FAINT, 1, dash=3, gap=3)
        for dx, dy2, player in ((-2.95, 0.9, 0), (2.95, -0.85, 1), (3.1, 0.95, 1)):
            _marble(surface, (cx + gap * dx, cy + gap * dy2), r0, player, alpha=90)

        # 中央那一手：三枚推一枚，被推的那枚正被顶向盘外
        start = at(1.75)
        end = (cx + gap * 3.25, cy)
        _dashed(surface, [start, end], theme.ACCENT, 2)
        _arrow(surface, end, 0.0, theme.ACCENT, 6)

    def _icon_hive(self, surface, rect: pygame.Rect) -> None:
        """昆虫棋：蜂后被围了五面，只差一面 —— 缺口旁边还有虚线格可以往外长。

        蜂巢是从已有棋子长出来的，画满反而像固定棋盘，所以边上留白 + 虚线格。
        """
        cx, cy = rect.centerx, rect.centery
        size = 13.0
        # 与 games/hive/geometry.py 同一套 pointy-top 换算；这里不 import 规则包，
        # 免得大厅反过来依赖某个具体棋类
        span_x, span_y = size * 1.732, size * 1.5
        directions = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
        gap_dir = (0, 1)  # 剩下没被占的那一面

        def centre(q: float, r: float) -> tuple[float, float]:
            return (cx + span_x * (q + r / 2.0), cy + span_y * r)

        # 六面里已经占掉五面：四周都是玩家 1 的虫（围杀不分敌我，这里全是围方）
        for q, r in directions:
            if (q, r) == gap_dir:
                continue
            pygame.draw.polygon(surface, theme.PLAYER_COLORS[0],
                                _hex_points(centre(q, r), size - 1.0))
            pygame.draw.polygon(surface, theme.PLAYER_DARK[0],
                                _hex_points(centre(q, r), size - 1.0), 1)
        # 中央那枚是对方的蜂后：描一圈亮边，别和"普通格子"混在一起
        pygame.draw.polygon(surface, theme.PLAYER_COLORS[1], _hex_points(centre(0, 0), size - 1.0))
        pygame.draw.polygon(surface, theme.PLAYER_DARK[1], _hex_points(centre(0, 0), size - 1.0), 1)
        pygame.draw.polygon(surface, theme.SELECT_RING, _hex_points(centre(0, 0), size - 2.0), 2)

        # 缺口：虚线轮廓 + 提示色 —— 这就是"还差一面"
        points = _hex_points(centre(*gap_dir), size - 1.0)
        _dashed(surface, [*points, points[0]], theme.OK, 2, dash=4, gap=3)

        # 无边界：外围两个虚线格，说明蜂巢还能往外长
        for gq, gr in ((2, 0), (-2, 1)):
            pts = _hex_points(centre(gq, gr), size - 1.0)
            _dashed(surface, [*pts, pts[0]], theme.TEXT_FAINT, 1, dash=3, gap=4)

    def _icon_dots(self, surface, rect: pygame.Rect) -> None:
        """兜底：3×3 圆角方块，对角线提亮。"""
        size = 14
        gap = 22
        cx, cy = rect.centerx, rect.centery
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pos = (cx + dx * gap - size // 2, cy + dy * gap - size // 2)
                color = theme.ACCENT if dx == dy else theme.ACCENT_DIM
                render.rounded_rect(surface, pygame.Rect(pos, (size, size)), color, 3)

    def _icon_dotsboxes(self, surface, rect: pygame.Rect) -> None:
        """点格棋：4×4 点阵 + 已画的边 + 一个刚被占领的方格。

        画的边用墙金色（与对局里"画边"同色），占领格是琥珀玩家的半透明填充，
        表达"画满四条边即占格"。
        """
        rows = cols = 4
        pitch = 20
        cx, cy = rect.centerx, rect.centery
        left = cx - (cols - 1) * pitch / 2
        top = cy - (rows - 1) * pitch / 2

        def at(c: int, r: int) -> tuple[float, float]:
            return (left + c * pitch, top + r * pitch)

        # 占领格（左上 2×2 区域里的一格）：琥珀色半透明
        bx0, by0 = at(1, 1)
        box = pygame.Rect(bx0 - pitch / 2, by0 - pitch / 2, pitch, pitch)
        layer = pygame.Surface((pitch, pitch), pygame.SRCALPHA)
        pygame.draw.rect(layer, (*theme.PLAYER_COLORS[0], 70), layer.get_rect())
        surface.blit(layer, box.topleft)

        # 已画的边：围绕占领格的一圈 + 右下一条散边
        edge_color = theme.WALL_EDGE
        for (c0, r0, c1, r1) in (
            (0, 1, 1, 1), (0, 2, 1, 2), (0, 1, 0, 2), (1, 1, 1, 2),
            (2, 2, 3, 2), (3, 2, 3, 3),
        ):
            pygame.draw.line(surface, edge_color, at(c0, r0), at(c1, r1), 3)

        # 点阵
        for r in range(rows):
            for c in range(cols):
                pygame.draw.circle(surface, theme.TEXT_DIM, at(c, r), 3)

    def _icon_mancala(self, surface, rect: pygame.Rect) -> None:
        """播棋：上排 4 个小坑 + 两端仓库 + 种子圆点。

        上排是玩家 2（蓝）的坑，右下角仓库显示已收的种子 —— 一句话就是
        "把种子搬进自己仓库"。
        """
        cx, cy = rect.centerx, rect.centery
        pitch = 26
        pit_r = 10
        store_r = 16

        # 两端仓库：左蓝右琥珀（对局里玩家 0 在下排靠左，这里用左右区分）
        left_store = (cx - pitch * 2.2, cy)
        right_store = (cx + pitch * 2.2, cy)
        for center, player in ((left_store, 1), (right_store, 0)):
            layer = pygame.Surface((store_r * 2, store_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*theme.PLAYER_COLORS[player], 60),
                               (store_r, store_r), store_r)
            surface.blit(layer, (center[0] - store_r, center[1] - store_r))
            pygame.draw.circle(surface, theme.PLAYER_COLORS[player], center, store_r, 2)
            # 仓库里的种子
            pygame.draw.circle(surface, theme.PLAYER_COLORS[player],
                               (int(center[0]), int(center[1])), 4)

        # 上排 4 个小坑，其中两个有种子
        seeds_in = {1: 3, 3: 2}
        for i in range(4):
            x = cx - pitch * 1.5 + i * pitch
            y = cy - pitch * 0.9
            pygame.draw.circle(surface, theme.CELL_ALT, (int(x), int(y)), pit_r)
            pygame.draw.circle(surface, theme.BORDER, (int(x), int(y)), pit_r, 2)
            n = seeds_in.get(i, 0)
            for k in range(n):
                sx = x + (k - (n - 1) / 2) * 6
                pygame.draw.circle(surface, theme.WALL, (int(sx), int(y)), 2)

        # 下排 3 个小坑，其中一个有种子
        for i in range(3):
            x = cx - pitch + i * pitch
            y = cy + pitch * 0.9
            pygame.draw.circle(surface, theme.CELL_ALT, (int(x), int(y)), pit_r)
            pygame.draw.circle(surface, theme.BORDER, (int(x), int(y)), pit_r, 2)
            if i == 0:
                pygame.draw.circle(surface, theme.WALL, (int(x - 3), int(y)), 2)
                pygame.draw.circle(surface, theme.WALL, (int(x + 3), int(y + 2)), 2)


# --------------------------------------------------------------------------- #
# 图标用的小工具（都不画文字）
# --------------------------------------------------------------------------- #

def _marble(
    surface,
    center: tuple[float, float],
    radius: int,
    player: int,
    alpha: int = 255,
) -> None:
    """一枚棋子：深色描边 + 玩家色本体（半透明时自己开一层）。

    描边**按半径取比例**（大约 1/4）而不是写死 2px —— 图标里的子只有 5px 半径，
    固定 2px 描边会把本体挤成一个小点，整个图标看起来像"一盘黑点"。
    """
    pos = (int(round(center[0])), int(round(center[1])))
    inner = max(2, radius - max(1, radius // 4))
    if alpha >= 255:
        pygame.draw.circle(surface, theme.PLAYER_DARK[player], pos, radius)
        pygame.draw.circle(surface, theme.PLAYER_COLORS[player], pos, inner)
        return
    pad = radius + 2
    layer = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*theme.PLAYER_DARK[player], alpha), (pad, pad), radius)
    pygame.draw.circle(layer, (*theme.PLAYER_COLORS[player], alpha), (pad, pad), inner)
    surface.blit(layer, (pos[0] - pad, pos[1] - pad))


def _dashed(
    surface,
    points,
    color: tuple[int, int, int],
    width: int = 2,
    dash: int = 5,
    gap: int = 4,
) -> None:
    """沿折线画虚线（pygame 没有虚线绘制）。"""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) < 2:
        return
    on = True
    phase = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            continue
        ux, uy = dx / length, dy / length
        travelled = 0.0
        while travelled < length:
            want = (dash if on else gap) - phase
            step = min(want, length - travelled)
            if on:
                pygame.draw.line(
                    surface, color,
                    (x0 + ux * travelled, y0 + uy * travelled),
                    (x0 + ux * (travelled + step), y0 + uy * (travelled + step)),
                    width,
                )
            travelled += step
            phase += step
            if phase >= (dash if on else gap) - 1e-9:
                on = not on
                phase = 0.0


def _arrow(
    surface,
    tip: tuple[float, float],
    angle: float,
    color: tuple[int, int, int],
    size: int = 6,
) -> None:
    """一个小箭头（只画三角，不画杆 —— 杆由 :func:`_dashed` 负责）。"""
    spread = 0.42
    p1 = (tip[0] - size * math.cos(angle - spread), tip[1] - size * math.sin(angle - spread))
    p2 = (tip[0] - size * math.cos(angle + spread), tip[1] - size * math.sin(angle + spread))
    pygame.draw.polygon(surface, color, [tip, p1, p2])


def _hex_points(center: tuple[float, float], size: float) -> list[tuple[float, float]]:
    """pointy-top 六边形的六个顶点（尖朝上）。"""
    cx, cy = center
    half = 0.8660254 * size
    return [
        (cx, cy - size),
        (cx + half, cy - size / 2),
        (cx + half, cy + size / 2),
        (cx, cy + size),
        (cx - half, cy + size / 2),
        (cx - half, cy - size / 2),
    ]
