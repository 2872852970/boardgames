"""步步为营的棋盘渲染与交互。

**全程鼠标，用右键切换"放墙模式"**：

* 右键开 / 关放墙模式（放下一面墙后会自动退出，一回合只需要放一面）；
* 放墙模式下：鼠标吸附到**最近的内部网格交点**，画出幽灵墙预览
  （绿色=可放，红色=不可放），点一下即落墙；**四个格子的公共交点同样有提示**；
* 非放墙模式：只高亮合法走子落点，点一下即走子（含跳跃）。

朝向（横 / 竖）带有**滞回**：一旦在某个交点选定了朝向，鼠标只是轻微抖动不会换朝向，
必须明显偏向另一条网格线才会切换 —— 否则在交点附近预览会在横竖之间疯狂跳。

``QuoridorView`` 自己管朝向的滞回状态；是否处于放墙模式由 ``ViewState.extra["wall_mode"]``
统一持有（和窗口 / 侧栏共享）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from boardgames.core.move import Move
from boardgames.games.quoridor.geometry import HORIZONTAL, VERTICAL, Wall
from boardgames.games.quoridor.move import PawnMove, WallMove
from boardgames.games.quoridor.state import QuoridorState
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween, ease_out_back, ease_out_cubic, lerp_pos
from boardgames.ui.board_view import PLACEMENT_MODE_KEY, ViewState
from boardgames.ui.fonts import FontBook

#: 放墙模式下鼠标吸附范围（单位：格）。每个内部交点负责它周围 1×1 格的方形区域，
#: 因此鼠标在棋盘内部任何位置都能吸附到唯一的交点，不会出现"有提示 / 没提示"的跳变。
WALL_SNAP_ZONE = 0.45
#: 朝向滞回阈值：只有明显偏向另一条网格线才换朝向，避免在交点附近抖动
ORIENT_HYSTERESIS = 0.12
#: 刚放下的那面墙，鼠标还停在这个范围内就不再提示
JUST_PLACED_RADIUS = 0.75

WALL_MODE_KEY = PLACEMENT_MODE_KEY
"""兼容别名：历史名。新代码请用 :data:`~boardgames.ui.board_view.PLACEMENT_MODE_KEY`。"""


def _round_half_up(value: float) -> int:
    """四舍五入（Python 的 round 是银行家舍入，会左右不对称）。"""
    return int(math.floor(value + 0.5))


@dataclass
class _WallAnim:
    wall: Wall
    tween: Tween


@dataclass
class _Intent:
    """鼠标当前位置想做什么。"""

    kind: str = "none"  # "wall" | "cell" | "none"
    cell: tuple[int, int] | None = None
    wall: Wall | None = None
    legal: bool = False


class QuoridorView:
    """Quoridor 的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 600)
        self.cell = 48
        self.origin = (0, 0)
        self.size = 9
        self._anim_pawn: tuple[PawnMove, Tween] | None = None
        self._anim_wall: _WallAnim | None = None
        self._last_move: Move | None = None
        # 悬停状态
        self._hover_wall: Wall | None = None
        self._hover_legal = False
        self._hover_target: tuple[int, int] | None = None
        self._hover_kind = "none"
        self._intent_state: QuoridorState | None = None
        #: 刚放下的墙：鼠标还停在这附近时不重复提示
        self._just_placed_wall: Wall | None = None
        #: 朝向滞回状态（当前吸附的交点 + 已选定朝向 + 是否被手动锁定）
        self._wall_anchor: tuple[int, int] | None = None
        self._wall_orient: str = HORIZONTAL
        self._orient_locked = False
        # 走子落点缓存
        self._cache_state: QuoridorState | None = None
        self._pawn_targets: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        span = min(area.width, area.height)
        self.cell = max(12, int(span / (self.size + 0.45)))
        board = self.cell * self.size
        self.origin = (
            area.x + (area.width - board) // 2,
            area.y + (area.height - board) // 2,
        )

    def set_size(self, size: int) -> None:
        self.size = size
        self.layout(self.area)

    @property
    def wall_thickness(self) -> int:
        return max(6, int(self.cell * 0.24))

    def cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(
            self.origin[0] + x * self.cell,
            self.origin[1] + y * self.cell,
            self.cell,
            self.cell,
        )

    def cell_center(self, x: int, y: int) -> tuple[int, int]:
        return (
            self.origin[0] + int((x + 0.5) * self.cell),
            self.origin[1] + int((y + 0.5) * self.cell),
        )

    def anchor_center(self, wall: Wall) -> tuple[int, int]:
        _, ax, ay = wall
        return (
            self.origin[0] + int((ax + 1) * self.cell),
            self.origin[1] + int((ay + 1) * self.cell),
        )

    def wall_rect(self, wall: Wall, *, inflate: int = 0) -> pygame.Rect:
        orient, _ax, _ay = wall
        cx, cy = self.anchor_center(wall)
        gap = max(4, int(self.cell * 0.16))
        t = self.wall_thickness
        if orient == HORIZONTAL:
            w = 2 * self.cell - gap + inflate
            h = t + inflate
        else:
            w = t + inflate
            h = 2 * self.cell - gap + inflate
        return pygame.Rect(cx - w // 2, cy - h // 2, w, h)

    # ------------------------------------------------------------------ #
    # 鼠标 → 坐标
    # ------------------------------------------------------------------ #

    def _fractional(self, pos: tuple[int, int]) -> tuple[float, float]:
        return (
            (pos[0] - self.origin[0]) / self.cell,
            (pos[1] - self.origin[1]) / self.cell,
        )

    def cell_at(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        fx, fy = self._fractional(pos)
        x, y = math.floor(fx), math.floor(fy)
        if 0 <= x < self.size and 0 <= y < self.size:
            return (x, y)
        return None

    # ------------------------------------------------------------------ #
    # 悬停意图：放墙模式吸附交点，否则只做走子
    # ------------------------------------------------------------------ #

    def _intent(self, pos: tuple[int, int], game, state: QuoridorState, view: ViewState) -> _Intent:
        if not isinstance(state, QuoridorState):
            return _Intent("none")
        size = state.size
        fx, fy = self._fractional(pos)
        if not (-0.5 <= fx <= size + 0.5 and -0.5 <= fy <= size + 0.5):
            return _Intent("none")

        cell = self.cell_at(pos)

        if not view.flag(WALL_MODE_KEY, False):
            if cell is None:
                return _Intent("none")
            return _Intent("cell", cell, None, cell in self._targets(game, state))

        # ---- 放墙模式：吸附到最近的**内部**网格交点（棋盘外框上没有墙槽）----
        line_x = min(max(_round_half_up(fx), 1), size - 1)
        line_y = min(max(_round_half_up(fy), 1), size - 1)
        wall = self._sticky_wall(line_x, line_y, fx, fy)
        if wall == self._just_placed_wall:
            return _Intent("none")  # 刚放下的那面墙不再重复提示
        # 不可放时也给出预览（红色 + 叉），让用户看得到"这里放不了"
        legal = game.is_wall_legal(state, state.current_player, wall)
        return _Intent("wall", cell, wall, legal)

    def _sticky_wall(self, line_x: int, line_y: int, fx: float, fy: float) -> Wall:
        """在交点附近挑选朝向时加滞回，避免鼠标轻微移动就在横 / 竖之间跳。"""
        anchor = (line_x - 1, line_y - 1)
        if self._wall_anchor != anchor:
            # 换了一个交点 → 按"离哪条线更近"重新决定朝向（一样近时默认横墙），
            # 并且解除手动锁定
            self._wall_anchor = anchor
            self._orient_locked = False
            dist_v = abs(fx - line_x)
            dist_h = abs(fy - line_y)
            self._wall_orient = HORIZONTAL if dist_h <= dist_v else VERTICAL
        elif not self._orient_locked:
            dist_v = abs(fx - line_x)
            dist_h = abs(fy - line_y)
            if self._wall_orient == HORIZONTAL:
                if dist_v < dist_h - ORIENT_HYSTERESIS:
                    self._wall_orient = VERTICAL
            elif dist_h < dist_v - ORIENT_HYSTERESIS:
                self._wall_orient = HORIZONTAL
        return (self._wall_orient, anchor[0], anchor[1])

    def flip_orientation(self) -> str:
        """手动翻转待放墙的朝向（V 键），并锁定到离开当前交点为止。"""
        self._wall_orient = VERTICAL if self._wall_orient == HORIZONTAL else HORIZONTAL
        self._orient_locked = True
        return self._wall_orient

    def _refresh_intent(self, pos, game, state, view: ViewState) -> _Intent:
        intent = self._intent(pos, game, state, view)
        self._intent_state = state
        self._hover_kind = intent.kind
        self._hover_legal = intent.legal
        self._hover_wall = intent.wall if intent.kind == "wall" else None
        self._hover_target = intent.cell if (intent.kind == "cell" and intent.legal) else None
        view.extra["hover_kind"] = intent.kind
        return intent

    def _targets(self, game, state: QuoridorState) -> set[tuple[int, int]]:
        """当前玩家的合法走子落点（含跳跃落点），按局面缓存。"""
        if self._cache_state is not state:
            self._cache_state = state
            self._pawn_targets = {
                move.dst for move in game.pawn_moves_for(state, state.current_player)
            }
        return self._pawn_targets

    def handle_motion(self, pos, game, state, view: ViewState) -> None:
        view.mouse = pos
        # 鼠标离开刚放下的那面墙附近后，恢复正常提示
        if self._just_placed_wall is not None:
            cx, cy = self.anchor_center(self._just_placed_wall)
            reach = self.cell * JUST_PLACED_RADIUS
            if abs(pos[0] - cx) > reach or abs(pos[1] - cy) > reach:
                self._just_placed_wall = None
        self._refresh_intent(pos, game, state, view)

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, QuoridorState):
            return None
        intent = self._refresh_intent(pos, game, state, view)
        player = state.current_player

        if intent.kind == "wall" and intent.wall is not None:
            if not intent.legal:
                return None
            # 记下来：鼠标不挪开就不再对这个位置给提示
            self._just_placed_wall = intent.wall
            return WallMove(*intent.wall)

        if intent.cell is not None and intent.cell in self._targets(game, state):
            return PawnMove(state.pawns[player], intent.cell)
        return None

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        """给棋盘 HUD 用的一句话提示。"""
        if view.flag(WALL_MODE_KEY, False):
            if self._hover_wall is None:
                return "右键退出放墙模式", theme.TEXT_FAINT
            kind = "横墙" if self._hover_wall[0] == HORIZONTAL else "竖墙"
            if self._hover_legal:
                return f"点击放置{kind}（V 键换朝向）", theme.OK
            return f"{kind}不可放", theme.BAD
        if self._hover_target is not None:
            return "点击走子", theme.ACCENT
        return "右键进入放墙模式", theme.TEXT_FAINT

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #

    def animate(self, move: Move, duration_ms: int) -> None:
        if duration_ms <= 0:
            return
        tween = Tween(duration_ms / 1000.0)
        if isinstance(move, PawnMove):
            self._anim_pawn = (move, tween)
        elif isinstance(move, WallMove):
            self._anim_wall = _WallAnim(move.wall, tween)

    def update(self, dt_ms: float) -> bool:
        busy = False
        if self._anim_pawn is not None:
            move, tween = self._anim_pawn
            tween.update(dt_ms / 1000.0)
            if tween.done:
                self._anim_pawn = None
            else:
                busy = True
        if self._anim_wall is not None:
            self._anim_wall.tween.update(dt_ms / 1000.0)
            if self._anim_wall.tween.done:
                self._anim_wall = None
            else:
                busy = True
        return busy

    def is_animating(self) -> bool:
        return self._anim_pawn is not None or self._anim_wall is not None

    def reset(self) -> None:
        self._anim_pawn = None
        self._anim_wall = None
        self._hover_wall = None
        self._hover_target = None
        self._hover_kind = "none"
        self._hover_legal = False
        self._cache_state = None
        self._intent_state = None
        self._just_placed_wall = None
        self._wall_anchor = None
        self._orient_locked = False
        self._last_move = None

    def set_last_move(self, move: Move | None) -> None:
        self._last_move = move

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def draw(
        self,
        surface: pygame.Surface,
        fonts: FontBook,
        game,
        state: QuoridorState,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        if state.size != self.size:
            self.set_size(state.size)
        # 局面变了（落子 / 悔棋 / 新局）就按当前鼠标位置重算悬停意图，保证预览不过期
        if self._intent_state is not state:
            self._refresh_intent(view.mouse, game, state, view)

        board = pygame.Rect(
            self.origin[0], self.origin[1], self.cell * self.size, self.cell * self.size
        )
        outer = board.inflate(self.wall_thickness + 14, self.wall_thickness + 14)
        render.panel(surface, outer, color=theme.BOARD_BG, radius=theme.RADIUS + 6)

        wall_mode = bool(view.flag(WALL_MODE_KEY, False))
        self._draw_goal_rows(surface, board, state)
        self._draw_cells(surface, state)
        self._draw_slots(surface, state)
        self._draw_walls(surface, state)
        if interactive:
            self._draw_ghost(surface)
        self._draw_last_move(surface, state)
        if interactive and not wall_mode:
            # 放墙模式下不显示走子落点，避免和幽灵墙混淆
            self._draw_hints(surface, state, game)
        self._draw_pawns(surface, state, interactive)
        frame_color = theme.OK if wall_mode else theme.BORDER
        render.rounded_rect(surface, board.inflate(6, 6), frame_color, theme.RADIUS, width=1)

    # ---- 各图层 ----

    def _draw_goal_rows(self, surface, board: pygame.Rect, state: QuoridorState) -> None:
        for player in (0, 1):
            row = state.goal_row(player)
            tint = theme.GOAL_TINT_P0 if player == 0 else theme.GOAL_TINT_P1
            rect = pygame.Rect(board.x, board.y + row * self.cell, board.width, self.cell)
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            layer.fill((*tint, 200))
            surface.blit(layer, rect.topleft)

    def _draw_cells(self, surface, state: QuoridorState) -> None:
        for y in range(state.size):
            for x in range(state.size):
                rect = self.cell_rect(x, y)
                color = theme.CELL if (x + y) % 2 == 0 else theme.CELL_ALT
                if state.pawns[0] == (x, y):
                    color = theme.mix(color, theme.P0, 0.10)
                elif state.pawns[1] == (x, y):
                    color = theme.mix(color, theme.P1, 0.10)
                render.rounded_rect(surface, rect.inflate(-3, -3), color, 6)

    def _draw_slots(self, surface, state: QuoridorState) -> None:
        """墙槽位：在每个内部网格交点上画一个小点，提示"边缘可以放墙"。"""
        w = state.size - 1
        radius = max(1, self.wall_thickness // 6)
        for ay in range(w):
            for ax in range(w):
                cx, cy = self.anchor_center((HORIZONTAL, ax, ay))
                pygame.draw.circle(surface, theme.BORDER, (cx, cy), radius)

    def _draw_walls(self, surface, state: QuoridorState) -> None:
        anim_wall = self._anim_wall.wall if self._anim_wall is not None else None
        anim_t = self._anim_wall.tween.eased(ease_out_back) if self._anim_wall is not None else 1.0
        w = state.size - 1
        for orient, mask in ((HORIZONTAL, state.h_mask), (VERTICAL, state.v_mask)):
            for ay in range(w):
                for ax in range(w):
                    if not (mask >> (ay * w + ax)) & 1:
                        continue
                    wall = (orient, ax, ay)
                    growing = anim_wall == wall
                    inflate = int(-self.cell * 0.5 * (1 - anim_t)) if growing else 0
                    self._draw_wall(surface, wall, inflate=inflate, highlight=growing)

    def _draw_wall(self, surface, wall: Wall, *, inflate: int = 0, highlight: bool = False) -> None:
        rect = self.wall_rect(wall, inflate=inflate)
        render.rounded_rect(surface, rect.move(0, 3), theme.WALL_SHADOW, theme.RADIUS_SM)
        body = theme.WALL_EDGE if highlight else theme.WALL
        render.rounded_rect(surface, rect, body, theme.RADIUS_SM)
        top = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, max(1, rect.height // 3))
        render.rounded_rect(surface, top, theme.lighten(body, 0.25), theme.RADIUS_SM)

    def _draw_ghost(self, surface) -> None:
        if self._hover_wall is None:
            return
        color = theme.OK if self._hover_legal else theme.BAD
        rect = self.wall_rect(self._hover_wall)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        render.rounded_rect(layer, pygame.Rect(0, 0, *rect.size), (*color, 170), theme.RADIUS_SM)
        if not self._hover_legal:
            pygame.draw.line(layer, (*color, 235), (4, 4), (rect.width - 4, rect.height - 4), 2)
            pygame.draw.line(layer, (*color, 235), (rect.width - 4, 4), (4, rect.height - 4), 2)
        surface.blit(layer, rect.topleft)

    def _draw_last_move(self, surface, state: QuoridorState) -> None:
        move = self._last_move
        if isinstance(move, PawnMove):
            dest = self.cell_rect(*move.dst).inflate(-6, -6)
            render.rounded_rect(surface, dest, theme.mix(theme.BG, theme.ACCENT, 0.35), 6, width=2)
        elif isinstance(move, WallMove):
            rect = self.wall_rect(move.wall, inflate=5)
            render.rounded_rect(surface, rect, theme.mix(theme.BG, theme.WALL, 0.5),
                                theme.RADIUS_SM, width=2)

    def _draw_hints(self, surface, state: QuoridorState, game) -> None:
        for target in self._targets(game, state):
            center = self.cell_center(*target)
            hovered = target == self._hover_target
            radius = 10 if hovered else 6
            color = theme.mix(theme.BG, theme.HINT_DOT, 0.95 if hovered else 0.5)
            pygame.draw.circle(surface, color, center, radius)
            if hovered:
                pygame.draw.circle(surface, theme.HINT_DOT, center, radius + 3, 2)

    def _draw_pawns(self, surface, state: QuoridorState, interactive: bool) -> None:
        for player in (0, 1):
            pos = state.pawns[player]
            center = self.cell_center(*pos)
            if self._anim_pawn is not None:
                move, tween = self._anim_pawn
                if state.pawns[player] == move.dst:
                    t = tween.eased(ease_out_cubic)
                    center = tuple(
                        int(v)
                        for v in lerp_pos(
                            self.cell_center(*move.src), self.cell_center(*move.dst), t
                        )
                    )
            self._draw_pawn(
                surface, center, player, interactive and player == state.current_player
            )

    def _draw_pawn(self, surface, center, player: int, active: bool) -> None:
        radius = max(8, int(self.cell * 0.33))
        color = theme.PLAYER_COLORS[player]
        dark = theme.PLAYER_DARK[player]
        if active:
            render.circle_glow(surface, center, radius, color, layers=5, max_alpha=110)
        pygame.draw.circle(surface, theme.darken(dark, 0.35), (center[0], center[1] + 3), radius)
        pygame.draw.circle(surface, dark, center, radius)
        pygame.draw.circle(surface, color, center, radius - 2)
        pygame.draw.circle(surface, theme.lighten(color, 0.35),
                           (center[0] - radius // 3, center[1] - radius // 3), max(2, radius // 3))
        if active:
            pygame.draw.circle(surface, theme.SELECT_RING, center, radius + 3, 2)


def make_view() -> QuoridorView:
    """视图工厂（注册表用）。"""
    return QuoridorView()


__all__ = ["WALL_MODE_KEY", "QuoridorView", "make_view"]
