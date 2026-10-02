"""主窗口：主循环、事件分发、场景与联调。"""

from __future__ import annotations

import time

import pygame

from boardgames.controller import GameSession
from boardgames.core.registry import GameRegistry
from boardgames.games.quoridor.view import WALL_MODE_KEY
from boardgames.settings import Settings
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween, ease_out_cubic
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook
from boardgames.ui.sidebar import Sidebar, Status
from boardgames.ui.widgets import Button

#: 改变这些参数需要重开一局（它们决定棋局的初始构造）
RESTART_KEYS = {"board_size", "walls_per_player", "first_player"}
#: 这些参数一改就作废正在进行的搜索（换了引擎 / 不再是 AI 的回合）
MODE_KEYS = {"mode", "p1_type", "p2_type", "first_player"}
#: 这些参数一改就让正在思考的 AI 重新思考
AI_KEYS_PREFIX = ("minimax_", "mcts_", "w_", "p_wall", "ai_seed")


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


class _Toast:
    """棋盘底部的一行短暂提示。"""

    def __init__(self) -> None:
        self.text = ""
        self.tween = Tween(0.0)
        self.until = 0.0

    def show(self, text: str, seconds: float = 1.6) -> None:
        self.text = text
        self.until = time.monotonic() + seconds

    def active(self) -> bool:
        return bool(self.text) and time.monotonic() < self.until

    def alpha(self) -> int:
        remaining = self.until - time.monotonic()
        fade = max(0.0, min(1.0, remaining / 0.4))
        return int(220 * ease_out_cubic(fade))


class GameWindow:
    """把 session、视图、侧栏和主循环串起来。"""

    def __init__(
        self,
        settings: Settings,
        registry: GameRegistry,
        game_key: str = "quoridor",
        *,
        headless: bool = False,
        window_size: tuple[int, int] | None = None,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("棋类游戏 · 步步为营")
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
        self.session = GameSession(settings, registry, game_key)

        factory = registry.view_factory(game_key)
        self.view = factory() if factory is not None else None
        if self.view is None:
            raise RuntimeError(f"游戏 {game_key!r} 没有注册棋盘视图")

        self.view_state = ViewState()
        self.sidebar = Sidebar(settings, self._on_setting, self._on_action)
        self.toast = _Toast()
        self.running = True
        self.clock = pygame.time.Clock()
        self._dirty_since: float | None = None
        self._last_move = None

        self._overlay_buttons = [
            Button("再来一局", lambda: self._on_action("new_game", None), variant="primary"),
            Button("悔棋", lambda: self._on_action("undo", None)),
        ]
        self._layout()
        self._sync_view_flags()

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def _layout(self) -> None:
        width, height = self.screen.get_size()
        # 窗口偏窄时侧栏按比例收窄，把空间让给棋盘
        sidebar_w = max(theme.SIDEBAR_MIN_W, min(theme.SIDEBAR_W, int(width * 0.34)))
        sidebar_w = min(sidebar_w, max(theme.SIDEBAR_MIN_W, width - 360))
        sidebar_rect = pygame.Rect(width - sidebar_w, 0, sidebar_w, height)
        margin = theme.BOARD_MARGIN
        board_rect = pygame.Rect(0, 0, width - sidebar_w, height).inflate(-margin * 2, -margin * 2)
        self.sidebar.layout(sidebar_rect)
        self.view.layout(board_rect)
        self.board_area = pygame.Rect(0, 0, width - sidebar_w, height)
        self.sidebar_rect = sidebar_rect
        self._layout_overlay_buttons()

    def _layout_overlay_buttons(self) -> None:
        area = self.board_area
        center = area.center
        w, h, gap = 132, 40, 12
        total = w * 2 + gap
        left = center[0] - total // 2
        top = center[1] + 44
        self._overlay_buttons[0].layout(pygame.Rect(left, top, w, h))
        self._overlay_buttons[1].layout(pygame.Rect(left + w + gap, top, w, h))

    def _sync_view_flags(self) -> None:
        self.view_state.extra["show_hints"] = bool(self.settings.get("show_hints"))
        self.view_state.extra["show_wall_slots"] = bool(self.settings.get("show_wall_slots"))

    # ------------------------------------------------------------------ #
    # 侧栏回调
    # ------------------------------------------------------------------ #

    def _on_setting(self, key: str, value) -> None:
        self.settings.set(key, value)
        self._dirty_since = time.monotonic()
        self._sync_view_flags()
        if key in RESTART_KEYS:
            self._restart()
            self.toast.show("棋局设置已生效，已开新局")
        elif key == "mode":
            # 模式变了：作废正在进行的搜索，并让「自对弈默认暂停」重新生效
            self.session.cancel_thinking()
            self.session.paused = value == "eve"
            self.view_state.extra[WALL_MODE_KEY] = False
            if value == "eve":
                self.toast.show("AI 自对弈已暂停：点「单步」或点棋盘逐步推进")
        elif key in MODE_KEYS:
            # 换了引擎 / 不再是 AI 的回合：作废进行中的搜索
            self.session.cancel_thinking()
        elif key.startswith(AI_KEYS_PREFIX) and self.session.is_thinking():
            # 让新参数立即生效
            self.session.cancel_thinking()

    def _on_action(self, action: str, payload) -> None:
        if action == "new_game":
            self._restart()
            self.toast.show("新的一局")
        elif action == "undo":
            self._do_undo()
        elif action == "resign":
            self.session.resign()
        elif action == "step":
            if self.session.request_step():
                self.toast.show("单步：AI 思考中…")
            else:
                self.toast.show("先暂停才能单步推进")
        elif action == "toggle_pause":
            self.session.paused = not self.session.paused
            if self.session.paused:
                self.session.cancel_thinking()
            self.toast.show("已暂停" if self.session.paused else "继续")

    def _restart(self) -> None:
        self.session.new_game()
        self.view.reset()
        self.view_state.extra[WALL_MODE_KEY] = False
        self._last_move = None
        self.sidebar.sync_from_settings()
        if self.session.mode == "eve":
            self.toast.show("AI 自对弈已暂停：点「单步」或点棋盘逐步推进")

    def _do_undo(self) -> None:
        if not self.session.can_undo():
            self.toast.show("已经是开局，无法悔棋")
            return
        steps_before = len(self.session.history)
        if self.session.undo():
            self.view.reset()
            self.view_state.extra[WALL_MODE_KEY] = False
            removed = steps_before - len(self.session.history)
            self._last_move = self.session.history[-1].move
            self.view.set_last_move(self._last_move)
            self.toast.show(f"已悔棋 {removed} 步")

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
            elif event.type == pygame.KEYDOWN:
                # 侧栏有输入框在编辑时，键盘先给它（避免 Esc/字母 误触发快捷键）
                if not self.sidebar.handle_key(event):
                    self._handle_key(event)
            else:
                self._handle_pointer(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        session = self.session
        wall_mode = bool(self.view_state.extra.get(WALL_MODE_KEY, False))
        if event.key == pygame.K_ESCAPE:
            if wall_mode:
                self.view_state.extra[WALL_MODE_KEY] = False
                self.toast.show("已退出放墙模式")
            else:
                self.running = False
        elif event.key == pygame.K_v and wall_mode:
            orient = self.view.flip_orientation()
            self.toast.show("换成" + ("横墙" if orient == "h" else "竖墙"))
            self._refresh_hover()
        elif event.key == pygame.K_n:
            self._on_action("new_game", None)
        elif event.key == pygame.K_u:
            self._do_undo()
        elif event.key == pygame.K_r:
            self._on_action("resign", None)
        elif event.key in (pygame.K_SPACE, pygame.K_s) and session.mode == "eve":
            if event.key == pygame.K_s:
                self._on_action("step", None)
            else:
                self._on_action("toggle_pause", None)
        elif event.key == pygame.K_SPACE and session.is_over:
            self._on_action("toggle_pause", None)

    def _refresh_hover(self) -> None:
        """按当前鼠标位置重算悬停预览（切模式 / 换朝向 / 局面变化后调用）。"""
        self.view.handle_motion(
            self.view_state.mouse, self.session.game, self.session.state, self.view_state
        )

    def _toggle_wall_mode(self) -> None:
        if not self._interactive():
            self.toast.show(self._blocked_reason())
            return
        turning_on = not self.view_state.extra.get(WALL_MODE_KEY, False)
        self.view_state.extra[WALL_MODE_KEY] = turning_on
        self.toast.show(
            "放墙模式：移动鼠标预览，点击落墙（右键 / Esc 退出）" if turning_on else "已退出放墙模式"
        )
        self._refresh_hover()

    def _try_single_step(self) -> bool:
        """自对弈暂停时，点棋盘 = 单步推进。"""
        session = self.session
        if session.mode != "eve" or not session.paused or session.is_over:
            return False
        if session.request_step():
            self.toast.show("单步：AI 思考中…")
        return True

    def _handle_pointer(self, event: pygame.event.Event) -> None:
        if self.session.is_over:
            for button in self._overlay_buttons:
                if button.handle_event(event):
                    return

        if self.sidebar.handle_event(event):
            return

        if event.type == pygame.MOUSEMOTION:
            if self.board_area.collidepoint(event.pos):
                self.view.handle_motion(event.pos, self.session.game, self.session.state, self.view_state)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.board_area.collidepoint(event.pos):
                self._toggle_wall_mode()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.board_area.collidepoint(event.pos):
                return
            if self._try_single_step():
                return
            if not self._interactive():
                self.toast.show(self._blocked_reason())
                return
            move = self.view.handle_click(event.pos, self.session.game, self.session.state, self.view_state)
            if move is None:
                return
            if not self.session.is_legal(move):
                self.toast.show("这里放不下墙")
                return
            self._apply_move(move)

    def _apply_move(self, move) -> None:
        self.view.animate(move, int(self.settings.get("anim_ms")))
        self.view.set_last_move(move)
        self._last_move = move
        self.session.play(move)
        if move.is_placement:
            # 一回合只放一面墙：放完自动退出放墙模式
            self.view_state.extra[WALL_MODE_KEY] = False

    # ------------------------------------------------------------------ #
    # 更新
    # ------------------------------------------------------------------ #

    def _interactive(self) -> bool:
        session = self.session
        return (
            not session.is_over
            and not session.paused
            and session.is_human_turn()
            and not self.view.is_animating()
            and not session.is_thinking()
        )

    def _blocked_reason(self) -> str:
        session = self.session
        if session.is_over:
            return "对局已结束"
        if session.paused:
            return "已暂停：点「单步」或点棋盘推进"
        if session.is_thinking():
            return "AI 正在思考…"
        if self.view.is_animating():
            return "动画播放中…"
        if not session.is_human_turn():
            return "轮到 AI 行棋"
        return ""

    def _update(self, dt_ms: float) -> None:
        session = self.session
        self._sync_view_flags()
        self.view_state.input_locked = self.view.is_animating()
        self.view_state.interactive_player = (
            session.state.current_player if session.is_human_turn() else None
        )

        # AI 调度（暂停 / 单步由 session 自己判断）
        if not session.is_over and session.is_ai_turn():
            session.start_thinking()
        move = session.poll()
        if move is not None:
            self.view.animate(move, int(self.settings.get("anim_ms")))
            self.view.set_last_move(move)
            self._last_move = move

        self.view.update(dt_ms)

        mouse = pygame.mouse.get_pos()
        self.sidebar.status = self._build_status()
        self.sidebar.update(dt_ms, mouse)
        for button in self._overlay_buttons:
            button.visible = session.is_over
            button.update(dt_ms, mouse)

        self._maybe_save(dt_ms)

    def _build_status(self) -> Status:
        session = self.session
        state = session.state
        stats = session.last_stats
        walls = getattr(state, "walls_left", (0, 0))
        return Status(
            current_player=state.current_player,
            player_types=session.resolved_player_types(),
            walls_left=(walls[0], walls[1]),
            is_thinking=session.is_thinking(),
            thinking_player=state.current_player,
            thinking_elapsed_ms=session.thinking_elapsed_ms(),
            last_search=stats.summary() if stats is not None else "",
            winner_text=session.result_text(),
            is_over=session.is_over,
            paused=session.paused,
            can_undo=session.can_undo(),
            hint="把鼠标移到格子边缘可放墙，移到格子中心可走子",
            extras={"is_selfplay": session.mode == "eve"},
        )

    def _maybe_save(self, dt_ms: float) -> None:
        # 防抖 600ms 后落盘
        if self._dirty_since is not None and time.monotonic() - self._dirty_since > 0.6:
            self.settings.save()
            self._dirty_since = None

    def _flush_settings(self) -> None:
        self.settings.save()

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def _draw(self) -> None:
        self.screen.fill(theme.BG)
        session = self.session
        self.view.draw(
            self.screen,
            self.fonts,
            session.game,
            session.state,
            self.view_state,
            interactive=self._interactive(),
        )
        self._draw_board_hud()
        if session.is_over:
            self._draw_result_overlay()
        self.sidebar.draw(self.screen, self.fonts)
        self._draw_toast()

    def _draw_board_hud(self) -> None:
        """棋盘下方操作提示 + 左上角的悬停意图提示。"""
        area = self.board_area
        fonts = self.fonts
        wall_mode = bool(self.view_state.extra.get(WALL_MODE_KEY, False))
        if self.session.mode == "eve" and self.session.paused and not self.session.is_over:
            tip = "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        elif wall_mode:
            tip = "放墙模式：移动鼠标预览（绿可放 / 红不可放），点击落墙；右键或 Esc 退出，V 换朝向"
        else:
            tip = "点击高亮圆点走子；右键进入放墙模式"
        render.text(
            self.screen,
            fonts.get(13),
            tip,
            (area.centerx, area.bottom - 24),
            theme.OK if (wall_mode or self.session.paused) else theme.TEXT_FAINT,
            align="center",
            baseline="middle",
        )

        hint, color = ("", theme.TEXT_FAINT)
        if self._interactive() and hasattr(self.view, "hover_hint"):
            hint, color = self.view.hover_hint(self.view_state)
        chip = pygame.Rect(area.x + 18, area.y + 14, 210, 30)
        render.rounded_rect(self.screen, chip, theme.PANEL, theme.RADIUS_SM)
        if wall_mode:
            render.rounded_rect(self.screen, chip, theme.OK, theme.RADIUS_SM, width=1)
        render.text(
            self.screen,
            fonts.get(13),
            hint or ("放墙模式" if wall_mode else "走子模式"),
            chip.center,
            color if hint else (theme.OK if wall_mode else theme.TEXT_FAINT),
            align="center",
            baseline="middle",
        )

    def _draw_result_overlay(self) -> None:
        area = self.board_area
        veil = pygame.Surface(area.size, pygame.SRCALPHA)
        veil.fill((*theme.BG, 190))
        self.screen.blit(veil, area.topleft)

        card = pygame.Rect(0, 0, 420, 210)
        card.center = area.center
        render.panel(self.screen, card, color=theme.PANEL, radius=theme.RADIUS + 4)
        render.text(self.screen, self.fonts.get(24, bold=True), self.session.result_text(),
                    (card.centerx, card.y + 46), theme.TEXT, align="center", baseline="middle")
        render.text(self.screen, self.fonts.get(13), "按 U 悔棋复盘 · N 开新局",
                    (card.centerx, card.y + 84), theme.TEXT_DIM, align="center", baseline="middle")
        w, h, gap = 132, 40, 12
        total = w * 2 + gap
        left = card.centerx - total // 2
        for i, button in enumerate(self._overlay_buttons):
            button.layout(pygame.Rect(left + i * (w + gap), card.y + 128, w, h))
            button.draw(self.screen, self.fonts)

    def _draw_toast(self) -> None:
        if not self.toast.active():
            return
        area = self.board_area
        font = self.fonts.get(14)
        width = font.size(self.toast.text)[0] + 36
        rect = pygame.Rect(0, 0, width, 36)
        rect.center = (area.centerx, area.bottom - 26)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        render.rounded_rect(layer, pygame.Rect(0, 0, *rect.size), (*theme.PANEL, 235), theme.RADIUS_SM)
        render.rounded_rect(layer, pygame.Rect(0, 0, *rect.size), (*theme.BORDER, 200), theme.RADIUS_SM, 1)
        text_surface = font.render(self.toast.text, True, theme.TEXT)
        text_surface.set_alpha(self.toast.alpha())
        layer.blit(text_surface, (18, (rect.height - text_surface.get_height()) // 2))
        self.screen.blit(layer, rect.topleft)
