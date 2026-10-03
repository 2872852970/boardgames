"""游戏选择大厅：卡片网格 + 玩法简介。

卡片数据全部来自 :class:`~boardgames.core.game.Game` 上的元数据 ClassVar
（``tagline`` / ``summary`` / ``rules`` / ``icon``），由
:meth:`~boardgames.core.registry.GameRegistry.all_games` 遍历生成 ——
**以后再接第三个棋类，大厅这边零改动。**

交互
----
* 鼠标移到卡片上高亮，点击直接进对局；
* 键盘 ``←/→`` 行内移动、``↑/↓`` 跨行、``Enter/Space`` 进入、``Esc`` 退出程序；
* 小屏（``choose_window_size`` 裁剪后可能只剩 760×560）单列放不下时启用滚轮。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

from boardgames.ui import render, theme
from boardgames.ui.fonts import FontBook

if TYPE_CHECKING:  # 避免运行时循环 import
    from boardgames.core.game import Game
    from boardgames.ui.window import GameWindow

#: 卡片网格的排布断点（按可用宽度）
COLS_NARROW, COLS_MEDIUM = 760, 1080
#: 卡片尺寸上下限
CARD_MIN_W, CARD_MAX_W = 232, 320
CARD_MIN_H, CARD_MAX_H = 250, 330
CARD_GAP = 22
#: 标题区高度（从顶部留白到第一行卡片）
HEADER_SPACE = 108
#: 底部提示区
FOOTER_SPACE = 62
#: 卡片里示意图标区的高度
ICON_H = 88


@dataclass
class _Card:
    game: Game
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


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

    # ------------------------------------------------------------------ #
    # 场景接口
    # ------------------------------------------------------------------ #

    def on_enter(self) -> None:
        self._focus = 0
        self._hover = -1
        self.scroll = 0.0

    def on_exit(self) -> None:
        pass

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
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

        for i, card in enumerate(self._cards):
            card.rect = pygame.Rect(
                left + (i % cols) * (card_w + CARD_GAP),
                top + (i // cols) * (card_h + CARD_GAP) - int(self.scroll),
                card_w, card_h,
            )
        # 放不下时允许滚动（否则底部一排会画到屏幕外）
        viewport_bottom = area.bottom - FOOTER_SPACE
        self.max_scroll = max(0.0, top + grid_h - viewport_bottom)
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def handle_event(self, event: pygame.event.Event) -> bool:
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

    # ------------------------------------------------------------------ #
    # 更新与绘制
    # ------------------------------------------------------------------ #

    def update(self, dt_ms: float) -> None:
        self._time += dt_ms / 1000.0

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
        self._draw_scrollbar(surface)

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
        bold = fonts.get(20, bold=True)

        # 先量一遍文本，算出内容实际需要多高 —— 卡片按内容收缩，
        # 否则下半部会留一大片空白。
        summary_lines = _wrap(body, getattr(game, "summary", ""), inner.width)
        rules = [r for r in getattr(game, "rules", ())[:3]
                 if body.size(render.truncate(body, r, inner.width - 16))[0] <= inner.width - 16]
        content_h = ICON_H + 6 + 26 + 22 + len(summary_lines) * 17 + 4 + len(rules) * 19 + pad

        # 内容比空间短时，把整块内容垂直居中
        top = inner.y + max(0, (inner.height - content_h) // 2)
        y = top

        # 示意图标
        icon_rect = pygame.Rect(inner.x, y, inner.width, ICON_H)
        self._draw_icon(surface, icon_rect, game.icon)
        y = icon_rect.bottom + 6

        render.text(surface, bold, game.display_name, (inner.x, y), theme.TEXT, baseline="middle")
        y += 26
        render.text(surface, fonts.get(12), game.tagline or game.key,
                    (inner.x, y), theme.TEXT_FAINT, baseline="middle")
        y += 22

        for line in summary_lines:
            render.text(surface, body, line, (inner.x, y), theme.TEXT_DIM, baseline="middle")
            y += 17
        y += 4

        for rule in rules:
            self._draw_bullet(surface, (inner.x + 5, y + 6), theme.ACCENT)
            render.text(surface, body, render.truncate(body, rule, inner.width - 16),
                        (inner.x + 16, y), theme.TEXT_FAINT, baseline="middle")
            y += 19

    def _draw_footer_hint(self, surface, fonts: FontBook) -> None:
        if not self._cards:
            render.text(surface, fonts.get(15), "还没有注册任何游戏",
                        (self.area.centerx, self.area.centery), theme.TEXT_FAINT,
                        align="center", baseline="middle")
            return
        render.text(
            surface, fonts.get(12),
            "点击卡片进入对局 · ←↑↓→ 选择 · Enter 确认 · Esc 退出",
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
    # 卡片图标（纯 pygame.draw，**不用文字 / emoji / 缺字形**）
    # ------------------------------------------------------------------ #

    def _draw_icon(self, surface, rect: pygame.Rect, kind: str) -> None:
        if kind == "drop":
            self._icon_drop(surface, rect)
        elif kind == "board":
            self._icon_board(surface, rect)
        else:
            self._icon_dots(surface, rect)

    def _icon_board(self, surface, rect: pygame.Rect) -> None:
        """Quoridor：3×3 点阵 + 一段墙。"""
        cx, cy = rect.centerx, rect.centery
        gap = 22
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pygame.draw.circle(surface, theme.TEXT_FAINT, (cx + dx * gap, cy + dy * gap), 3)
        # 在 (0,0)-(1,0) 之间放一段横墙
        wall = pygame.Rect(cx - gap, cy - 3, gap * 2, 6)
        render.rounded_rect(surface, wall.move(0, 2), theme.WALL_SHADOW, 3)
        render.rounded_rect(surface, wall, theme.WALL, 3)
        render.rounded_rect(surface, pygame.Rect(wall.x + 2, wall.y + 1, wall.width - 4, 2),
                            theme.WALL_EDGE, 2)

    def _icon_drop(self, surface, rect: pygame.Rect) -> None:
        """Connect Four：4×3 圆点阵 + 一颗正在下落的棋子。"""
        cols, rows = 4, 3
        gap = 24
        radius = 6
        cx = rect.centerx
        top = rect.centery - rows * gap // 2
        left = cx - (cols - 1) * gap // 2
        for r in range(rows):
            for c in range(cols):
                pos = (left + c * gap, top + r * gap)
                pygame.draw.circle(surface, theme.CELL_ALT, pos, radius)
        # 已落的棋子（底行左右各一）
        for c, player in ((0, 0), (3, 1)):
            pygame.draw.circle(surface, theme.PLAYER_DARK[player],
                               (left + c * gap, top + (rows - 1) * gap), radius)
            pygame.draw.circle(surface, theme.PLAYER_COLORS[player],
                               (left + c * gap, top + (rows - 1) * gap), radius - 2)
        # 正在下落：悬在中上方 + 两道运动线
        fall_col = 2
        fall_x = left + fall_col * gap
        fall_y = top - gap
        for offset in (10, 20):
            pygame.draw.line(surface, theme.BORDER_SOFT, (fall_x, fall_y - offset),
                             (fall_x, fall_y - offset + 5), 1)
        pygame.draw.circle(surface, theme.PLAYER_DARK[1], (fall_x, fall_y), radius)
        pygame.draw.circle(surface, theme.PLAYER_COLORS[1], (fall_x, fall_y), radius - 2)

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

    @staticmethod
    def _draw_bullet(surface, center, color) -> None:
        pygame.draw.circle(surface, color, center, 3)


def _wrap(font, text: str, max_width: int) -> list[str]:
    """按宽度折行（项目里没有自动换行工具）。

    中文没有空格，逐字断行会把句末的「。」孤零零甩到下一行 ——
    所以先尝试在标点处断开，找不到合适位置才逐字断。
    """
    if not text or font.size(text)[0] <= max_width:
        return [text] if text else []
    # 先在标点处切一刀，避免「。」独占一行
    pieces: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if ch in "，。；、：！？」』）":
            pieces.append(text[start:i + 1])
            start = i + 1
    if start < len(text):
        pieces.append(text[start:])

    lines: list[str] = []
    current = ""
    for piece in pieces:
        if font.size(current + piece)[0] <= max_width:
            current += piece
            continue
        if current:
            lines.append(current)
            current = ""
        # 单个片段还是太宽（长英文词）→ 逐字断
        for ch in piece:
            if current and font.size(current + ch)[0] > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
    if current:
        lines.append(current)
    return lines
