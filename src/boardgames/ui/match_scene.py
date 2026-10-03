"""对局场景：棋盘 + 侧栏 + AI 调度 + 结算浮层。

从原来的 :class:`~boardgames.ui.window.GameWindow` 里搬出来的。
关键约定（都是踩过的坑，搬的时候别顺手"优化"掉）：

* ``MOUSEBUTTONUP`` 必须**无条件**派发给控件 —— 只在鼠标位于侧栏内时派发的话，
  "在侧栏外松开左键"会让滑块永远停在拖拽态，之后不按键鼠标一动就改数值。
* ``WALL_MODE_KEY`` 改成 ``PLACEMENT_MODE_KEY``（放在 ``ui.board_view``），
  ``quoridor`` 保留同名别名，因此 8 个直接引用它的测试一行都不用改。
* 侧栏的「墙 N」是墙棋专属文案，改成由 :class:`Status.player_details` 提供。

摄像机（无边界棋盘）
--------------------
昆虫棋没有固定棋盘，视角归玩家控制。视图只要暴露一个 ``camera`` 属性
（:class:`~boardgames.ui.camera.Camera`），本场景就会自动接上：

* 滚轮缩放、按住左键 / 中键拖拽平移；
* 左键的"点击 / 拖拽"由 :class:`CameraController` 裁决 —— 位移小于阈值才算点击，
  所以"手抖一下"不会走错子；
* 开局自动适配（``camera.auto_fit``），玩家一上手就交还控制权，按 F 键收回。

没有 ``camera`` 的棋类（墙棋 / 四子棋 / 大力士棋）完全走原路径，一行都不动。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

from boardgames.controller import GameSession
from boardgames.core.move import Move
from boardgames.settings import Settings
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween, ease_out_cubic
from boardgames.ui.board_view import PLACEMENT_MODE_KEY, ViewState
from boardgames.ui.camera import CLICK, CONSUME, CameraController
from boardgames.ui.fonts import FontBook
from boardgames.ui.rules_panel import RulesOverlay
from boardgames.ui.sidebar import Sidebar, Status
from boardgames.ui.widgets import Button

if TYPE_CHECKING:  # 避免运行时循环 import
    from boardgames.ui.window import GameWindow

#: 改变这些参数需要重开一局（它们决定棋局的初始构造）
RESTART_KEYS = {"board_size", "walls_per_player", "first_player",
                "connect4_cols", "connect4_rows", "abalone_setup", "hive_expansion"}
#: 这些参数一改就作废正在进行的搜索（换了引擎 / 不再是 AI 的回合）
MODE_KEYS = {"mode", "p1_type", "p2_type", "first_player"}
#: 这些参数一改就让正在思考的 AI 重新思考。
#: ``"p_"`` 同时覆盖墙棋的 ``p_wall`` 与昆虫棋的 ``p_hive_place``（都是 rollout 偏好）
AI_KEYS_PREFIX = ("minimax_", "mcts_", "w_", "p_", "ai_seed")
#: 棋盘右上角「规则说明」按钮的宽度
RULES_BUTTON_W = 92


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


class MatchScene:
    """一局对局的全部界面逻辑。"""

    def __init__(self, window: GameWindow, game_key: str = "quoridor") -> None:
        self.window = window
        self.settings: Settings = window.settings
        self.game_key = game_key

        self.session = GameSession(window.settings, window.registry, game_key)
        factory = window.registry.view_factory(game_key)
        self.view = factory() if factory is not None else None
        if self.view is None:
            raise RuntimeError(f"游戏 {game_key!r} 没有注册棋盘视图")

        self.view_state = ViewState()
        game = self.session.game
        self.sidebar = Sidebar(
            window.settings, self._on_setting, self._on_action,
            game_key=game_key, game_title=game.display_name, game_tagline=game.tagline,
        )
        self.toast = _Toast()
        self._last_move: Move | None = None
        self._dirty_since: float | None = None
        self.board_area = pygame.Rect(0, 0, 600, 600)
        self.sidebar_rect = pygame.Rect(0, 0, theme.SIDEBAR_W, theme.WINDOW_H)

        # 摄像机是**可选**能力：有 ``view.camera`` 才接上（目前只有昆虫棋）
        self.camera = getattr(self.view, "camera", None)
        self._cam = CameraController(self.camera) if self.camera is not None else None

        self._overlay_buttons = [
            Button("再来一局", lambda: self._on_action("new_game", None), variant="primary"),
            Button("悔棋", lambda: self._on_action("undo", None)),
        ]
        # 规则说明：大厅能开，对局里也得能开 —— 下到一半忘了规则是最常见的场景。
        # 同一个浮层组件，谁都能持有一个实例。
        self.rules = RulesOverlay()
        self._rules_button = Button("规则说明", self._open_rules)
        self._apply_view_flags()

    # ------------------------------------------------------------------ #
    # 场景接口
    # ------------------------------------------------------------------ #

    def on_enter(self) -> None:
        self._apply_view_flags()

    def on_exit(self) -> None:
        # 必须停掉后台 AI 线程：否则它会继续跑并持有旧局面的引用
        self.session.cancel_thinking()
        self.rules.close()

    def layout(self, area: pygame.Rect) -> None:
        width, height = area.width, area.height
        # 窗口偏窄时侧栏按比例收窄，把空间让给棋盘
        sidebar_w = max(theme.SIDEBAR_MIN_W, min(theme.SIDEBAR_W, int(width * 0.34)))
        sidebar_w = min(sidebar_w, max(theme.SIDEBAR_MIN_W, width - 360))
        self.sidebar_rect = pygame.Rect(width - sidebar_w, 0, sidebar_w, height)
        margin = theme.BOARD_MARGIN
        board_rect = pygame.Rect(0, 0, width - sidebar_w, height).inflate(
            -margin * 2, -margin * 2
        )
        self.sidebar.layout(self.sidebar_rect)
        self.view.layout(board_rect)
        if self._cam is not None:
            # 视口默认就是整块棋盘区；视图可以自己收窄（昆虫棋要把底部手牌条
            # 排除在外，否则在卡片上拖动会被当成拖画布）
            viewport = getattr(self.view, "camera_viewport", None)
            self._cam.camera.set_viewport(viewport() if callable(viewport) else board_rect)
        self.board_area = pygame.Rect(0, 0, width - sidebar_w, height)
        self._layout_overlay_buttons()
        self.rules.layout(pygame.Rect(0, 0, width, height))

    def handle_event(self, event: pygame.event.Event) -> bool:
        # 规则浮层是模态的：开着的时候它吃掉全部事件，棋盘 / 侧栏都不再响应
        if self.rules.open:
            self.rules.handle_event(event)
            return True
        if event.type == pygame.KEYDOWN:
            # 侧栏有输入框在编辑时，键盘先给它（避免 Esc/N/U 误触发）
            if not self.sidebar.handle_key(event):
                self._handle_key(event)
            return True
        self._handle_pointer(event)
        return True

    def update(self, dt_ms: float) -> None:
        session = self.session
        self._apply_view_flags()
        self.view_state.input_locked = self.view.is_animating()
        self.view_state.interactive_player = (
            session.state.current_player if session.is_human_turn() else None
        )

        # AI 调度（暂停 / 单步由 session 自己判断）
        if not session.is_over and session.is_ai_turn():
            session.start_thinking()
        move = session.poll()
        if move is not None:
            self._play_move(move)

        self._auto_fit_camera()
        self.view.update(dt_ms)

        mouse = pygame.mouse.get_pos()
        self.sidebar.status = self._build_status()
        self.sidebar.update(dt_ms, mouse)
        for button in self._overlay_buttons:
            button.visible = session.is_over
            button.update(dt_ms, mouse)
        self._rules_button.update(dt_ms, mouse)
        self.rules.update(dt_ms, mouse)

    def draw(self, surface: pygame.Surface, fonts: FontBook) -> None:
        surface.fill(theme.BG)
        session = self.session
        # 始终从 window.screen 读 surface，不要缓存引用 ——
        # 测试里会直接 set_mode 换掉窗口表面
        self.view.draw(
            surface, fonts, session.game, session.state, self.view_state,
            interactive=self._interactive(),
        )
        self._draw_board_hud(surface, fonts)
        if session.is_over:
            self._draw_result_overlay(surface, fonts)
        self.sidebar.draw(surface, fonts)
        self._draw_toast(surface, fonts)
        self._rules_button.draw(surface, fonts)
        self.rules.draw(surface, fonts)

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    def _apply_view_flags(self) -> None:
        self.view_state.extra["show_hints"] = bool(self.settings.get("show_hints"))
        self.view_state.extra["show_wall_slots"] = bool(self.settings.get("show_wall_slots"))

    def _auto_fit_camera(self) -> None:
        """``camera.auto_fit`` 开着时把内容塞进视口 —— **但只在必要时**。

        三条"不许乱动镜头"的规则，每一条都对应一个真实踩过的坑：

        1. **鼠标按着的时候一帧都不许碰摄像机。** 主循环是"先派发事件、再
           ``update()``"，按下与松手天然落在相邻两帧；每帧重算就会把同一帧
           刚记下的"按下"抹掉，松手时看到"没按下过"于是什么都不做 ——
           点击被静默吞掉。表现就是**开局必须先滚一下滚轮才能落子**（滚轮会把
           ``auto_fit`` 置假，之后才不再每帧清手势）。
        2. **内容还看得见就别动。** 每帧重算的话，昆虫棋每落一子包围盒就变大
           一点，镜头跟着缩一点 —— 玩家看到的是"我刚落完子画面自己抖了一下"。
           只有内容真的跑出视口才收一次。
        3. 玩家一上手（滚轮 / 拖拽）就置 ``False``，之后再也不跟玩家抢镜头 ——
           只有按 F 或重开一局才收回。
        """
        if self._cam is None or not self.camera.auto_fit:
            return
        if self._cam.pressed:
            return
        bounds = self._content_bounds()
        if bounds is not None and self.camera.contains(bounds):
            return
        self._refit_camera()

    def _content_bounds(self) -> pygame.Rect | None:
        """内容的世界包围盒；视图没提供就返回 ``None``（= 每帧都适配）。

        固定棋盘的三家不需要这个钩子，它们本来就没有"内容会长出去"这回事。
        """
        hook = getattr(self.view, "world_bounds", None)
        if not callable(hook):
            return None
        try:
            return hook(self.session.state)
        except (TypeError, AttributeError):  # pragma: no cover - 视图钩子签名不符
            return None

    def _refit_camera(self) -> None:
        """把镜头拉回内容（同时重新交回自动适配）。

        "内容包围盒 + 边距"是**视图**知道的事（昆虫棋要把手牌条排除在外、
        还要给自动适配设一个软上限与最小可见跨度），所以优先问视图；
        视图没提供时退回通用做法。

        这里**刻意不调** ``self._cam.cancel()``：本方法每帧都会被自动适配
        调到，而 cancel 会顺手清掉进行中的手势（见 :meth:`_auto_fit_camera`）。
        要丢弃手势请显式调（换局 / 悔棋 / F 键）。
        """
        hook = getattr(self.view, "auto_fit_camera", None)
        if callable(hook):
            hook(self.session.state)
        else:  # pragma: no cover - 只暴露 camera 却没给适配规则的视图
            self.camera.fit(None)

    def _fit_camera(self) -> None:
        """F 键：把镜头拉回内容。"""
        if self._cam is None:
            return
        self._cam.cancel()  # 按 F 时手上可能还扣着一次拖拽，先丢掉
        self._refit_camera()
        self.toast.show("镜头已回到蜂巢")

    def _play_move(self, move: Move) -> None:
        """播放落子动画（AI 与人类走子都走这里）。"""
        self.view.animate(move, self._anim_ms())
        self.view.set_last_move(move)
        self._last_move = move

    def _anim_ms(self) -> int:
        """落子动画时长。

        四子棋用独立参数（``c4_anim_ms``，默认 850ms）—— 它的重力弹跳需要
        足够长的时间才看得清；大力士棋的整组滑行也需要比默认的 140ms 长一些
        （``abalone_anim_ms``，默认 260ms）；昆虫棋同样（``hive_anim_ms``）；
        墙棋沿用通用的 ``anim_ms``。
        """
        if self.game_key == "connect4":
            return int(self.settings.get("c4_anim_ms"))
        if self.game_key == "abalone":
            return int(self.settings.get("abalone_anim_ms"))
        if self.game_key == "hive":
            return int(self.settings.get("hive_anim_ms"))
        return int(self.settings.get("anim_ms"))

    def _place_mode_on(self) -> bool:
        """当前是否处于"放墙模式"。四子棋永远为 False。"""
        if not hasattr(self.view, "in_placement_mode"):
            return bool(self.view_state.extra.get(PLACEMENT_MODE_KEY, False))
        return bool(self.view.in_placement_mode())

    def _set_place_mode(self, on: bool) -> None:
        self.view_state.extra[PLACEMENT_MODE_KEY] = on

    def _layout_overlay_buttons(self) -> None:
        area = self.board_area
        center = area.center
        w, h, gap = 132, 40, 12
        total = w * 2 + gap
        left = center[0] - total // 2
        top = center[1] + 44
        self._overlay_buttons[0].layout(pygame.Rect(left, top, w, h))
        self._overlay_buttons[1].layout(pygame.Rect(left + w + gap, top, w, h))
        # 「规则说明」固定在棋盘右上角：左上角是悬停提示胶囊，底部是手牌条 / 提示行
        self._rules_button.layout(
            pygame.Rect(area.right - 18 - RULES_BUTTON_W, area.y + 14, RULES_BUTTON_W, 30)
        )

    def _open_rules(self) -> None:
        self.rules.show(self.session.game)

    # ------------------------------------------------------------------ #
    # 侧栏回调
    # ------------------------------------------------------------------ #

    def _on_setting(self, key: str, value) -> None:
        self.settings.set(key, value)
        self._dirty_since = time.monotonic()
        self._apply_view_flags()
        if key in RESTART_KEYS:
            self._restart()
            self.toast.show("棋局设置已生效，已开新局")
        elif key == "mode":
            # 模式变了：作废正在进行的搜索，并让「自对弈默认暂停」重新生效
            self.session.cancel_thinking()
            self.session.paused = value == "eve"
            self._set_place_mode(False)
            if value == "eve":
                self.toast.show("AI 自对弈已暂停：点「单步」或点棋盘逐步推进")
        elif key in MODE_KEYS or key.startswith(AI_KEYS_PREFIX) and self.session.is_thinking():
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
        elif action == "lobby":
            self.window.goto_lobby()

    def _restart(self) -> None:
        self.session.new_game()
        self.view.reset()
        if self.camera is not None:
            self.camera.auto_fit = True  # 新局重新交给自动适配，别停在上一局的角度
            if self._cam is not None:
                self._cam.cancel()
        self._set_place_mode(False)
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
            if self._cam is not None:
                self._cam.cancel()
            self._set_place_mode(False)
            removed = steps_before - len(self.session.history)
            self._last_move = self.session.history[-1].move
            self.view.set_last_move(self._last_move)
            self.toast.show(f"已悔棋 {removed} 步")

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #

    def _handle_key(self, event: pygame.event.Event) -> None:
        session = self.session
        if event.key == pygame.K_ESCAPE:
            # Esc 分级：先放下"举着的东西" → 再退放墙模式 → 再回大厅。
            # 不这么排的话，昆虫棋里想取消一次选子就得先被赶回大厅。
            if self._clear_selection():
                return
            if self._place_mode_on():
                self._set_place_mode(False)
                self.toast.show("已退出放墙模式")
            else:
                self.window.goto_lobby()
        elif self._pick_by_number(event.key):
            return
        elif event.key == pygame.K_v and self._place_mode_on():
            orient = self.view.flip_orientation()
            self.toast.show("换成" + ("横墙" if orient == "h" else "竖墙"))
            self._refresh_hover()
        elif event.key == pygame.K_w and self._place_mode_supported():
            # W = Wall：与右键等价的键盘入口（右键还要兼职"取消选择"）
            self._toggle_wall_mode()
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
        elif event.key == pygame.K_f and self._cam is not None:
            self._fit_camera()
        elif event.key in (pygame.K_h, pygame.K_SLASH):
            self._open_rules()

    def _clear_selection(self) -> bool:
        """放下当前"举着的东西"（手牌虫种 / 盘上棋子），返回是否真的放下了。

        用 ``hasattr`` 探测：只有实现了 ``has_selection`` 的视图（眼下是昆虫棋）
        才会让右键与 Esc 兼职"取消选择"。
        """
        if not hasattr(self.view, "has_selection") or not self.view.has_selection():
            return False
        self.view.clear_selection()
        self.toast.show("已取消选择")
        self._refresh_hover()
        return True

    def _pick_by_number(self, key: int) -> bool:
        """数字键 1..8 = 手牌条上的第 N 种虫（等价于点那张卡）；再按一次取消。

        返回 ``True`` 表示"这个键归我管了"，别让它落到别的分支上去。
        """
        if not (pygame.K_1 <= key <= pygame.K_8):
            return False
        if not (hasattr(self.view, "pick_kind") and hasattr(self.view, "active_hand_kinds")):
            return False
        state = self.session.state
        kinds = self.view.active_hand_kinds(state)
        index = key - pygame.K_1
        if index >= len(kinds):
            return True  # 这一局没这么多种虫 —— 照样吃掉，免得落到别的快捷键上
        if not self._interactive():
            self.toast.show(self._blocked_reason())
            return True
        label = self.view.pick_kind(kinds[index], self.session.game, state, self.view_state)
        self.toast.show(f"已选 {label}" if label else "已取消选择")
        self._refresh_hover()
        return True

    def _refresh_hover(self) -> None:
        """按当前鼠标位置重算悬停预览（切模式 / 换朝向 / 局面变化后调用）。"""
        self.view.handle_motion(
            self.view_state.mouse, self.session.game, self.session.state, self.view_state
        )

    def _toggle_wall_mode(self) -> None:
        if not self._interactive():
            self.toast.show(self._blocked_reason())
            return
        turning_on = not self._place_mode_on()
        self._set_place_mode(turning_on)
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
        if self._rules_button.handle_event(event):
            return

        if self.session.is_over:
            for button in self._overlay_buttons:
                if button.handle_event(event):
                    return

        if self.sidebar.handle_event(event):
            return

        # 摄像机优先：它会扣住左键直到松手，好区分"点击"与"拖拽画布"
        if self._cam is not None:
            verdict = self._cam.handle_event(event)
            if verdict == CONSUME:
                return
            if verdict == CLICK:
                self._board_click(event.pos)
                return

        if event.type == pygame.MOUSEMOTION:
            if self.board_area.collidepoint(event.pos):
                self.view.handle_motion(
                    event.pos, self.session.game, self.session.state, self.view_state
                )
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if not self.board_area.collidepoint(event.pos):
                return
            # 右键两种用途，按"当前有没有举着东西"分：先取消选择，否则才进放墙模式。
            # 四子棋两者都没有，右键就是什么都不做。
            if self._clear_selection():
                return
            if self._place_mode_supported():
                self._toggle_wall_mode()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.board_area.collidepoint(event.pos):
                return
            self._board_click(event.pos)

    def _board_click(self, pos: tuple[int, int]) -> None:
        """棋盘上的一次左键点击（摄像机裁决过"不是拖拽"之后才走到这里）。"""
        if self._try_single_step():
            return
        if not self._interactive():
            self.toast.show(self._blocked_reason())
            return
        move = self.view.handle_click(
            pos, self.session.game, self.session.state, self.view_state
        )
        if move is None:
            return
        if not self.session.is_legal(move):
            self.toast.show("这里放不下")
            return
        self._apply_move(move)

    def _place_mode_supported(self) -> bool:
        return not hasattr(self.view, "in_placement_mode")

    def _apply_move(self, move) -> None:
        self._play_move(move)
        self.session.play(move)
        if move.is_placement:
            # 一回合只放一面墙：放完自动退出放墙模式
            self._set_place_mode(False)

    # ------------------------------------------------------------------ #
    # 状态
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

    def _build_status(self) -> Status:
        session = self.session
        state = session.state
        stats = session.last_stats
        walls = getattr(state, "walls_left", (0, 0))
        details = self._player_details(state, walls)
        return Status(
            current_player=state.current_player,
            player_types=session.resolved_player_types(),
            walls_left=(walls[0], walls[1]),
            player_details=details,
            is_thinking=session.is_thinking(),
            thinking_player=state.current_player,
            thinking_elapsed_ms=session.thinking_elapsed_ms(),
            last_search=stats.summary() if stats is not None else "",
            winner_text=session.result_text(),
            is_over=session.is_over,
            paused=session.paused,
            can_undo=session.can_undo(),
            hint=self._hint_text(),
            extras={"is_selfplay": session.mode == "eve"},
        )

    def _player_details(self, state, walls) -> tuple[str, str]:
        """侧栏玩家行的详情（**只放数值部分**，类型标签由侧栏自己拼）。"""
        if self.game_key == "connect4":
            p0, p1 = state.count_pieces()
            return (f"已落 {p0} 子", f"已落 {p1} 子")
        if self.game_key == "abalone":
            # 大力士棋没有 walls_left，走通用分支会显示成"墙 0"
            return (f"挤出 {state.out[0]}/6", f"挤出 {state.out[1]}/6")
        if self.game_key == "hive":
            # 同理：昆虫棋既没有墙，胜负条件又是"围满蜂后"，
            # 所以直接把胜负进度摆在这里
            return tuple(
                f"围 {state.queen_surround(p)}/6 · 手牌 {state.hand_total(p)}" for p in (0, 1)
            )
        return (f"墙 {walls[0]}", f"墙 {walls[1]}")

    def _idle_label(self, place_mode: bool) -> str:
        """左上角胶囊在"鼠标没指向任何有意思的东西"时显示什么。

        默认的「投子」是四子棋的词 —— 别的棋类自己给一个，不然玩家以为
        点一下会往下扔东西。
        """
        if hasattr(self.view, "idle_hint"):
            return self.view.idle_hint()
        return "放墙模式" if place_mode else "投子"

    def _hint_text(self) -> str:
        if self.game_key == "connect4":
            return "把鼠标移到某一列会预览落点，点击投子"
        if self.game_key == "abalone":
            return "点己方棋子选组，再点虚线目标格走子"
        if self.game_key == "hive":
            return "点手牌或己方棋子 · 数字键 1-8 选虫种 · 右键取消 · 滚轮缩放、拖画布平移 · F 回正"
        return "把鼠标移到格子边缘可放墙，移到格子中心可走子"

    def _maybe_save(self, dt_ms: float) -> None:
        # 防抖 600ms 后落盘
        if self._dirty_since is not None and time.monotonic() - self._dirty_since > 0.6:
            self.settings.save()
            self._dirty_since = None

    # ------------------------------------------------------------------ #
    # 绘制细节
    # ------------------------------------------------------------------ #

    def _draw_board_hud(self, surface, fonts: FontBook) -> None:
        """棋盘下方操作提示 + 左上角的悬停意图提示。"""
        area = self.board_area
        place_mode = self._place_mode_on()
        if self.session.mode == "eve" and self.session.paused and not self.session.is_over:
            tip = "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        elif hasattr(self.view, "hud_hint"):
            tip = self.view.hud_hint(wall_mode=place_mode, paused=self.session.paused)
        elif place_mode:
            tip = "放墙模式：移动鼠标预览（绿可放 / 红不可放），点击落墙；右键 / W / Esc 退出，V 换朝向"
        else:
            tip = "点击高亮圆点走子；右键或 W 进入放墙模式（Esc 退出）"
        # 视图可以在底部留出自己的东西（昆虫棋的手牌条），提示得让开
        inset = self.view.hud_inset() if hasattr(self.view, "hud_inset") else 0
        render.text(
            surface, fonts.get(13), tip,
            (area.centerx, area.bottom - 24 - inset),
            theme.OK if (place_mode or self.session.paused) else theme.TEXT_FAINT,
            align="center", baseline="middle",
        )

        hint, color = ("", theme.TEXT_FAINT)
        if self._interactive() and hasattr(self.view, "hover_hint"):
            hint, color = self.view.hover_hint(self.view_state)
        # 胶囊宽度跟着文字走（旧的固定 210px 会把长提示从**两侧**截掉，
        # 看着像"文字跑到屏幕外面去了"）。太长时按可用宽度收窄并让 render.text
        # 自己裁切，至少不会顶出棋盘区域。
        font = fonts.get(13)
        label = hint or self._idle_label(place_mode)
        width = min(max(210, font.size(label)[0] + 26), max(120, area.width - 36))
        chip = pygame.Rect(area.x + 18, area.y + 14, width, 30)
        render.rounded_rect(surface, chip, theme.PANEL, theme.RADIUS_SM)
        if place_mode:
            render.rounded_rect(surface, chip, theme.OK, theme.RADIUS_SM, width=1)
        render.text(
            surface, font,
            label,
            chip.center,
            color if hint else (theme.OK if place_mode else theme.TEXT_FAINT),
            align="center", baseline="middle",
        )

    def _draw_result_overlay(self, surface, fonts: FontBook) -> None:
        area = self.board_area
        veil = pygame.Surface(area.size, pygame.SRCALPHA)
        veil.fill((*theme.BG, 190))
        surface.blit(veil, area.topleft)

        card = pygame.Rect(0, 0, 420, 210)
        card.center = area.center
        render.panel(surface, card, color=theme.PANEL, radius=theme.RADIUS + 4)
        render.text(surface, fonts.get(24, bold=True), self.session.result_text(),
                    (card.centerx, card.y + 46), theme.TEXT, align="center", baseline="middle")
        render.text(surface, fonts.get(13), "按 U 悔棋复盘 · N 开新局 · Esc 回大厅",
                    (card.centerx, card.y + 84), theme.TEXT_DIM, align="center", baseline="middle")
        w, h, gap = 132, 40, 12
        total = w * 2 + gap
        left = card.centerx - total // 2
        for i, button in enumerate(self._overlay_buttons):
            button.layout(pygame.Rect(left + i * (w + gap), card.y + 128, w, h))
            button.draw(surface, fonts)

    def _draw_toast(self, surface, fonts: FontBook) -> None:
        if not self.toast.active():
            return
        area = self.board_area
        font = fonts.get(14)
        width = font.size(self.toast.text)[0] + 36
        rect = pygame.Rect(0, 0, width, 36)
        rect.center = (area.centerx, area.bottom - 26)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        render.rounded_rect(layer, pygame.Rect(0, 0, *rect.size), (*theme.PANEL, 235),
                            theme.RADIUS_SM)
        render.rounded_rect(layer, pygame.Rect(0, 0, *rect.size), (*theme.BORDER, 200),
                            theme.RADIUS_SM, 1)
        text_surface = font.render(self.toast.text, True, theme.TEXT)
        text_surface.set_alpha(self.toast.alpha())
        layer.blit(text_surface, (18, (rect.height - text_surface.get_height()) // 2))
        surface.blit(layer, rect.topleft)
