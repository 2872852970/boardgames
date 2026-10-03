"""规则说明浮层 —— 大厅卡片与对局界面共用。

内容**全部来自** :class:`~boardgames.core.game.Game` 上的元数据 ClassVar
（``goal`` / ``summary`` / ``rules`` / ``howto`` / ``tips``），所以接第五个棋类时
这里零改动：把那些 ClassVar 写满就有了一份完整的规则说明。

为什么单独一个模块
------------------
大厅和对局都要能打开它，而两者都是 :class:`~boardgames.ui.scene.Scene`
（互相不知道对方的存在）。做成"谁都能持有一个实例、自己接管事件"的浮层，
比塞进某一个场景里再想办法让另一个场景调用要干净得多。

浮层打开时由持有者**最先**派发事件给它（见 :meth:`handle_event`），
关闭方式有意给了三种：右上角的 ×、点遮罩、Esc / 空格 —— 少一种都会有人在
某个界面里"关不掉"。
"""

from __future__ import annotations

import pygame

from boardgames.ui import render, theme
from boardgames.ui.fonts import FontBook
from boardgames.ui.widgets import Button

#: 卡片内边距与分节的间距
PAD = 24
SECTION_GAP = 14
LINE_H = 22
BULLET_GAP = 14
#: 关闭按钮
CLOSE_W, CLOSE_H = 96, 34
#: 标题栏（游戏名那一行）高度
HEAD_H = 58


def rules_sections(game) -> list[tuple[str, tuple[str, ...]]]:
    """把 ``Game`` 的元数据整理成「小节标题 → 条目」的列表。

    全空的棋类（还没写元数据）至少也会得到一节"敬请期待"，不会画出一个空面板。
    """
    sections: list[tuple[str, tuple[str, ...]]] = []
    goal = getattr(game, "goal", "")
    summary = getattr(game, "summary", "")
    rules = tuple(getattr(game, "rules", ()) or ())
    howto = tuple(getattr(game, "howto", ()) or ())
    tips = tuple(getattr(game, "tips", ()) or ())
    if goal:
        sections.append(("目标", (goal,)))
    if summary:
        sections.append(("简介", (summary,)))
    if rules:
        sections.append(("规则", rules))
    if howto:
        sections.append(("操作", howto))
    if tips:
        sections.append(("提示", tips))
    if not sections:
        sections.append(("规则", ("这个棋类还没写规则说明。",)))
    return sections


class RulesOverlay:
    """一块居中的规则说明卡片（带遮罩、滚动与关闭按钮）。"""

    def __init__(self, on_close=None) -> None:
        self.on_close = on_close
        self.game = None
        self._open = False
        #: 折行要量文字宽度，而 ``show()`` 拿不到窗口的 FontBook ——
        #: 自己留一份（FontBook 内部有缓存，多一份只是多几个 Font 对象）
        self._fonts = FontBook()
        self.area = pygame.Rect(0, 0, theme.WINDOW_W, theme.WINDOW_H)
        self._card = pygame.Rect(0, 0, 0, 0)
        self._close = Button("关闭", self.close, variant="primary")
        self.scroll = 0.0
        self.max_scroll = 0.0
        self._sections: list[tuple[str, tuple[str, ...]]] = []
        self._lines: list[tuple[str, str, int]] = []  # (类型, 文本, 缩进)
        self._content_h = 0

    # ------------------------------------------------------------------ #
    # 开关
    # ------------------------------------------------------------------ #

    @property
    def open(self) -> bool:
        return self._open

    def show(self, game) -> None:
        self.game = game
        self._sections = rules_sections(game)
        self.scroll = 0.0
        self._open = True
        self._relayout()

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self.scroll = 0.0
        if self.on_close is not None:
            self.on_close()

    def toggle(self, game) -> None:
        if self._open:
            self.close()
        else:
            self.show(game)

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._relayout()

    def _card_rect(self) -> pygame.Rect:
        """卡片尺寸：跟着窗口走，但不小于能读的下限。"""
        width = int(min(560, max(320, self.area.width - 96)))
        height = int(min(self.area.height - 64, max(300, self.area.height * 0.82)))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = self.area.center
        return rect

    def _relayout(self) -> None:
        if not self._open or self.game is None:
            return
        self._card = self._card_rect()
        inner_w = self._card.width - PAD * 2
        body = self._fonts.get(13)
        # 先按可用宽度把每行折好 —— 折行结果只和宽度有关，
        # 缓存下来就不用每帧重排（滚动时只改 y 偏移）。
        self._lines = []
        for title, items in self._sections:
            self._lines.append(("head", title, 0))
            for item in items:
                for line in render.wrap(body, item, inner_w - BULLET_GAP):
                    self._lines.append(("item", line, BULLET_GAP))
        viewport_h = self._content_viewport().height
        self._content_h = sum(
            LINE_H + 6 if kind == "head" else LINE_H for kind, _, _ in self._lines
        ) + 8
        self.max_scroll = max(0.0, self._content_h - viewport_h)
        self.scroll = max(0.0, min(self.max_scroll, self.scroll))
        self._close.layout(
            pygame.Rect(
                self._card.right - PAD - CLOSE_W,
                self._card.bottom - PAD - CLOSE_H,
                CLOSE_W, CLOSE_H,
            )
        )

    def _content_viewport(self) -> pygame.Rect:
        """正文的可视区（卡片去掉标题行与底部关闭条）。"""
        return pygame.Rect(
            self._card.x + PAD,
            self._card.y + HEAD_H,
            self._card.width - PAD * 2,
            self._card.height - HEAD_H - PAD - CLOSE_H - 12,
        )

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def handle_event(self, event: pygame.event.Event) -> bool:
        """打开时**吃掉所有事件**；没打开时一律返回 False（交给场景）。"""
        if not self._open:
            return False
        if self._close.handle_event(event):
            return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y * 44)
            return True
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if event.button in (4, 5):
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._scroll_by(-44 if event.button == 4 else 44)
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self._card.collidepoint(event.pos):
                    self.close()  # 点遮罩关闭
                return True
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER,
                             pygame.K_SPACE):
                self.close()
            return True
        return True

    def _scroll_by(self, delta: float) -> None:
        self.scroll = max(0.0, min(self.max_scroll, self.scroll + delta))

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def update(self, dt_ms: float, mouse: tuple[int, int]) -> None:
        if not self._open:
            return
        self._close.update(dt_ms, mouse)

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        if not self._open or self.game is None:
            return
        veil = pygame.Surface(self.area.size, pygame.SRCALPHA)
        veil.fill((*theme.BG, 205))
        surface.blit(veil, self.area.topleft)

        render.soft_shadow(surface, self._card, theme.RADIUS + 4, spread=5)
        render.rounded_rect(surface, self._card, theme.PANEL, theme.RADIUS + 4)
        render.rounded_rect(surface, self._card, theme.BORDER, theme.RADIUS + 4, width=1)

        # ---- 标题 ----
        title_x = self._card.x + PAD
        # 元数据一律 getattr：浮层不该因为某个棋类少写了一个 ClassVar 就崩掉
        name = getattr(self.game, "display_name", "") or getattr(self.game, "key", "规则说明")
        render.text(surface, fonts.get(20, bold=True), name,
                    (title_x, self._card.y + 22), theme.TEXT, baseline="middle")
        tagline = getattr(self.game, "tagline", "") or getattr(self.game, "key", "")
        name_w = fonts.get(20, bold=True).size(name)[0]
        render.text(surface, fonts.get(12), tagline,
                    (title_x + name_w + 12, self._card.y + 24), theme.TEXT_FAINT,
                    baseline="middle")
        pygame.draw.line(
            surface, theme.BORDER_SOFT,
            (self._card.x + PAD, self._card.y + HEAD_H - 10),
            (self._card.right - PAD, self._card.y + HEAD_H - 10),
        )

        # ---- 正文 ----
        viewport = self._content_viewport()
        clip = surface.get_clip()
        surface.set_clip(viewport)
        body = fonts.get(13)
        head = fonts.get(13, bold=True)
        y = viewport.y - int(self.scroll)
        for kind, line, indent in self._lines:
            if kind == "head":
                render.text(surface, head, line, (viewport.x, y + LINE_H // 2),
                            theme.ACCENT, baseline="middle")
                y += LINE_H + 6
                continue
            pygame.draw.circle(surface, theme.TEXT_FAINT,
                               (viewport.x + 5, y + LINE_H // 2), 2)
            render.text(surface, body, line, (viewport.x + indent, y + LINE_H // 2),
                        theme.TEXT_DIM, baseline="middle")
            y += LINE_H
        surface.set_clip(clip)

        # ---- 底部：滚动提示 + 关闭 ----
        if self.max_scroll > 1:
            render.text(
                surface, fonts.get(11),
                "滚轮翻页 · Esc 关闭",
                (self._card.x + PAD, self._close.rect.centery),
                theme.TEXT_FAINT, baseline="middle",
            )
        else:
            render.text(
                surface, fonts.get(11), "Esc 关闭",
                (self._card.x + PAD, self._close.rect.centery),
                theme.TEXT_FAINT, baseline="middle",
            )
        self._close.draw(surface, fonts)
        self._draw_scrollbar(surface)

    def _draw_scrollbar(self, surface) -> None:
        if self.max_scroll <= 1:
            return
        viewport = self._content_viewport()
        track = pygame.Rect(viewport.right + 8, viewport.y, 4, viewport.height)
        render.rounded_rect(surface, track, theme.PANEL_ALT, theme.RADIUS_PILL)
        frac = track.height / (track.height + self.max_scroll)
        knob_h = max(28, int(track.height * frac))
        offset = (track.height - knob_h) * (self.scroll / self.max_scroll)
        render.rounded_rect(
            surface,
            pygame.Rect(track.x, track.y + int(offset), track.width, knob_h),
            theme.BORDER, theme.RADIUS_PILL,
        )
