"""主窗口：窗口宿主 + 场景切换。

职责边界很硬
------------
本类**只**负责"窗口"这一层：screen、时钟、主循环、QUIT / VIDEORESIZE、
设置落盘。**画什么、响应什么**全部下发给 :attr:`GameWindow.scene`。

对局相关的逻辑都在 :class:`~boardgames.ui.match_scene.MatchScene` 里；
大厅在 :class:`~boardgames.ui.lobby.LobbyScene` 里。

转发 property
-------------
``window.session`` / ``window.view`` / ``window._update()`` 这些访问全部转发给
对局场景。这样既有的 UI 测试（两百多处 ``window.xxx`` 访问）一行都不用改，
同时场景本身又是独立可测的单元。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

from boardgames.core.registry import GameRegistry
from boardgames.settings import Settings
from boardgames.ui import theme
from boardgames.ui.fonts import FontBook
from boardgames.ui.scene import Scene

if TYPE_CHECKING:  # 避免运行时循环 import
    from boardgames.ui.lobby import LobbyScene
    from boardgames.ui.match_scene import MatchScene
    from boardgames.ui.sidebar import Sidebar


def desktop_size() -> tuple[int, int] | None:
    """当前桌面的可用像素尺寸（拿不到时返回 ``None``）。"""
    try:
        sizes = pygame.display.get_desktop_sizes()
    except (AttributeError, pygame.error):
        sizes = []
    if sizes:
        return sizes[0]
    try:
        info = pygame.display.Info()
    except pygame.error:
        return None
    if info.current_w > 0 and info.current_h > 0:
        return info.current_w, info.current_h
    return None


def choose_window_size(desktop: tuple[int, int] | None = None) -> tuple[int, int]:
    """窗口尺寸：默认值，但**绝不超出屏幕**。

    小屏 / 高 DPI 下如果直接用 1180×780，窗口底部（新局/悔棋/认输）会被屏幕裁掉，
    表现为"界面显示不全"。
    """
    width, height = theme.WINDOW_W, theme.WINDOW_H
    if desktop is None:
        desktop = desktop_size()
    if desktop is not None:
        dw, dh = desktop
        if dw > 0 and dh > 0:
            width = min(width, max(theme.MIN_WINDOW_W, int(dw * 0.94)), dw)
            height = min(height, max(theme.MIN_WINDOW_H, int(dh * 0.90)), dh)
    return width, height


#: 可选的初始场景。``match`` 直接进对局，``lobby`` 进游戏选择大厅。
START_SCENES = ("lobby", "match")


class GameWindow:
    """窗口宿主：主循环 + 场景切换。"""

    def __init__(
        self,
        settings: Settings,
        registry: GameRegistry,
        game_key: str = "quoridor",
        *,
        headless: bool = False,
        window_size: tuple[int, int] | None = None,
        start_scene: str = "match",
    ) -> None:
        """创建窗口。

        ``start_scene`` 默认是 ``"match"``（直接进对局）—— 仅为兼容既有的
        UI 测试夹具，它们假定 ``window.session`` 立刻可用。**产品入口
        （:func:`boardgames.app.main`）请显式传 ``start_scene="lobby"``**。
        """
        pygame.init()
        flags = 0 if headless else pygame.RESIZABLE
        if window_size is not None:
            size = (int(window_size[0]), int(window_size[1]))
        elif headless:
            size = (theme.WINDOW_W, theme.WINDOW_H)
        else:
            size = choose_window_size()
        self.screen = pygame.display.set_mode(size, flags)
        self.fonts = FontBook()
        self.settings = settings
        self.registry = registry
        self.game_key = game_key
        self.running = True
        self.clock = pygame.time.Clock()
        self._dirty_since: float | None = None

        # 对局场景**总是**创建：大厅里点卡片要能直接进对局，
        # 所以切过去时不需要临时构造。
        from boardgames.ui.match_scene import MatchScene

        self.match: MatchScene = MatchScene(self, game_key)
        self.lobby: LobbyScene | None = None
        self.scene: Scene = self.match if start_scene == "match" else self._build_lobby()
        self.scene.on_enter()
        self.scene.layout(self.screen.get_rect())
        self._apply_caption()

    # ------------------------------------------------------------------ #
    # 场景切换
    # ------------------------------------------------------------------ #

    def _build_lobby(self) -> LobbyScene:
        if self.lobby is None:
            from boardgames.ui.lobby import LobbyScene

            self.lobby = LobbyScene(self)
        return self.lobby

    def goto_lobby(self) -> None:
        """回到游戏选择大厅。"""
        if self.scene is self.lobby:
            return
        self._switch(self._build_lobby())

    def goto_match(self, game_key: str | None = None) -> None:
        """进入对局。``game_key`` 省略时沿用当前棋类。"""
        if game_key is not None and game_key != self.game_key:
            self.game_key = game_key
            from boardgames.ui.match_scene import MatchScene

            self.match = MatchScene(self, game_key)
        elif self.scene is self.match:
            self.match._restart()
        self._switch(self.match)

    def _switch(self, scene: Scene) -> None:
        self.scene.on_exit()
        self.scene = scene
        scene.on_enter()
        scene.layout(self.screen.get_rect())
        self._apply_caption()

    def _in_lobby(self) -> bool:
        return self.lobby is not None and self.scene is self.lobby

    def _apply_caption(self) -> None:
        if self._in_lobby():
            pygame.display.set_caption("棋类游戏 · 选棋")
        else:
            game = self.registry.get(self.game_key)
            pygame.display.set_caption(f"棋类游戏 · {game.display_name}")

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #

    def run(self, max_frames: int | None = None) -> None:
        frames = 0
        while self.running:
            dt_ms = self.clock.tick(theme.FPS)
            dt_ms = min(dt_ms, 100)  # 切后台回来防跳帧
            self._handle_events()
            self._update(dt_ms)
            self._draw()
            pygame.display.flip()
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        self._flush_settings()
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._layout()
            else:
                self.scene.handle_event(event)

    def _update(self, dt_ms: float) -> None:
        self.scene.update(dt_ms)
        self._maybe_save()

    def _draw(self) -> None:
        self.scene.draw(self.screen, self.fonts)

    def _layout(self) -> None:
        self.scene.layout(self.screen.get_rect())

    def _maybe_save(self, dt_ms: float = 0.0) -> None:
        # 防抖 600ms 后落盘
        if self._dirty_since is not None and time.monotonic() - self._dirty_since > 0.6:
            self.settings.save()
            self._dirty_since = None

    def _flush_settings(self) -> None:
        self.settings.save()

    # ------------------------------------------------------------------ #
    # 转发到对局场景（供既有测试与少量外部调用使用）
    # ------------------------------------------------------------------ #

    @property
    def session(self):
        return self.match.session

    @property
    def view(self):
        return self.match.view

    @property
    def sidebar(self) -> Sidebar:
        return self.match.sidebar

    @property
    def view_state(self):
        return self.match.view_state

    @property
    def board_area(self):
        return self.match.board_area

    @property
    def sidebar_rect(self):
        return self.match.sidebar_rect

    @property
    def toast(self):
        return self.match.toast

    def _on_setting(self, key: str, value) -> None:
        self.match._on_setting(key, value)

    def _on_action(self, action: str, payload) -> None:
        self.match._on_action(action, payload)

    def _interactive(self) -> bool:
        return self.match._interactive()

    def _restart(self) -> None:
        self.match._restart()
