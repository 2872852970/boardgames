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

import contextlib
import os
import time
from typing import TYPE_CHECKING

import pygame

from boardgames.core.registry import GameRegistry
from boardgames.settings import Settings
from boardgames.ui import theme
from boardgames.ui.chrome import TITLEBAR_H, TitleBar
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


def _use_dummy_driver() -> None:
    """切到 SDL 的 dummy 驱动（没有显示设备时唯一能开 surface 的办法）。"""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.display.quit()
    pygame.display.init()


def _open_screen(
    size: tuple[int, int], flags: int, offscreen: bool
) -> tuple[bool, pygame.Surface]:
    """开一块用于绘制的 surface，返回 ``(是否离屏, surface)``。

    ``offscreen`` 是**主动**要求的（CI / 跑批 / 截图脚本）；没要求但开不出来时
    （没有显示器、在容器里、远程桌面断开）也会自动切 dummy 兜底 ——
    "一启动就报 No available video device" 对谁都没好处。
    """
    if offscreen:
        _use_dummy_driver()
        return True, pygame.display.set_mode(size, flags)
    try:
        return False, pygame.display.set_mode(size, flags)
    except pygame.error:
        _use_dummy_driver()
        return True, pygame.display.set_mode(size, flags)


class GameWindow:
    """窗口宿主：主循环 + 场景切换。"""

    def __init__(
        self,
        settings: Settings,
        registry: GameRegistry,
        game_key: str = "quoridor",
        *,
        frameless: bool = False,
        offscreen: bool = False,
        window_size: tuple[int, int] | None = None,
        start_scene: str = "match",
    ) -> None:
        """创建窗口。

        * ``frameless``：**不要系统的标题栏**（``pygame.NOFRAME``），改由
          :class:`~boardgames.ui.chrome.TitleBar` 自己画一条（含关闭 / 全屏 /
          最小化 / 拖动）。窗口照常显示、照常能玩 —— 只是那条系统标题头没了。
        * ``offscreen``：压根不显示窗口（SDL dummy 驱动），给 CI 与跑批用。

        ``start_scene`` 默认是 ``"match"``（直接进对局）—— 仅为兼容既有的
        UI 测试夹具，它们假定 ``window.session`` 立刻可用。**产品入口
        （:func:`boardgames.app.main`）请显式传 ``start_scene="lobby"``**。
        """
        pygame.init()
        self.frameless = bool(frameless)
        self.offscreen = bool(offscreen)
        #: 无边框时自绘标题栏；有系统标题栏时为 ``None``。
        #: **必须在开窗口之前置好** —— ``_flags()`` 会读它，而 ``_open_screen``
        #: 又要用 ``_flags()``。
        self.titlebar: TitleBar | None = None
        size = (int(window_size[0]), int(window_size[1])) if window_size is not None else choose_window_size()
        self.offscreen, self.screen = _open_screen(size, self._flags(), offscreen)
        self._size = size
        #: 进全屏前的窗口尺寸，退出全屏时还原
        self._windowed_size = size
        if self.frameless:
            self.titlebar = TitleBar(
                on_close=self._close_window,
                on_minimize=self.minimize,
                on_maximize=self.toggle_fullscreen,
            )
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
        self._relayout()
        self._apply_caption()

    # ------------------------------------------------------------------ #
    # 窗口本身
    # ------------------------------------------------------------------ #

    def _flags(self) -> int:
        """``set_mode`` 的 flags。

        无边框 = ``NOFRAME``（系统标题栏没了，换成自己画的）；全屏是在这之上
        再加 ``FULLSCREEN``，所以退出全屏只要去掉这一位就行。

        ``FULLSCREEN`` 必须配 ``SCALED``：单用 ``FULLSCREEN`` 会**真的切换显示模式**
        （实测把 1280×720 的桌面切成 1024×640），而 ``FULLSCREEN | SCALED`` 是
        SDL2 的"桌面全屏"—— 不改分辨率，把逻辑画面缩放到整个桌面。
        """
        flags = pygame.NOFRAME if self.frameless else pygame.RESIZABLE
        if self.titlebar is not None and self.titlebar.fullscreen:
            # SCALED 需要渲染器，dummy 驱动下会警告 "no fast renderer"—— 离屏时干脆不要它
            scaled = 0 if self.offscreen else getattr(pygame, "SCALED", 0)
            flags |= pygame.FULLSCREEN | scaled
        return flags

    @property
    def content_rect(self) -> pygame.Rect:
        """场景可用的区域（无边框时要给自绘标题栏让出顶部那一条）。"""
        rect = self.screen.get_rect()
        if self.titlebar is not None:
            return pygame.Rect(rect.x, rect.y + TITLEBAR_H,
                               rect.width, max(40, rect.height - TITLEBAR_H))
        return rect

    def _relayout(self) -> None:
        if self.titlebar is not None:
            self.titlebar.layout(self.screen.get_rect())
        self.scene.layout(self.content_rect)

    def _close_window(self) -> None:
        self.running = False

    def minimize(self) -> None:
        with contextlib.suppress(pygame.error):  # 某些驱动不支持
            pygame.display.iconify()

    def toggle_fullscreen(self) -> None:
        """全屏 ↔ 窗口。无边框模式下"最大化"就等于全屏（没有边框可贴）。

        进全屏时把逻辑分辨率也换成桌面尺寸（配合 ``SCALED`` 就是 1:1，不糊），
        退出时按进入前的尺寸还原。
        """
        if self.titlebar is None:
            return
        entering = not self.titlebar.fullscreen
        target = (desktop_size() or self._size) if entering else self._windowed_size
        self.titlebar.fullscreen = entering
        try:
            self.screen = pygame.display.set_mode(target, self._flags())
        except pygame.error:  # pragma: no cover - 某些驱动不支持全屏
            self.titlebar.fullscreen = not entering
            return
        if entering:
            self._windowed_size = self._size
        self._size = target
        self._relayout()

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
        self._relayout()
        self._apply_caption()

    def _in_lobby(self) -> bool:
        return self.lobby is not None and self.scene is self.lobby

    def _apply_caption(self) -> None:
        # 无边框模式下系统标题栏看不见，但 caption 仍然有用：
        # 任务栏 / 窗口列表读它，测试也读它（test_caption_follows_scene）。
        if self._in_lobby():
            title = "棋类游戏 · 选棋"
        else:
            game = self.registry.get(self.game_key)
            title = f"棋类游戏 · {game.display_name}"
        pygame.display.set_caption(title)
        if self.titlebar is not None:
            self.titlebar.set_title(title)

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
                self._size = (event.size[0], event.size[1])
                self.screen = pygame.display.set_mode(event.size, self._flags())
                self._layout()
            elif self.titlebar is not None and self.titlebar.handle_event(event):
                continue  # 标题栏自己消化掉了（它只认落在自己那一条里的鼠标事件）
            else:
                self.scene.handle_event(event)

    def _update(self, dt_ms: float) -> None:
        self.scene.update(dt_ms)
        self._maybe_save()

    def _draw(self) -> None:
        self.scene.draw(self.screen, self.fonts)
        if self.titlebar is not None:
            self.titlebar.draw(self.screen, self.fonts)

    def _layout(self) -> None:
        self._relayout()

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
