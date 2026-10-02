"""步步为营的棋盘渲染与交互。

**全程鼠标操作，不需要任何"放墙模式"**：

* 鼠标移到**格子边缘**（靠近网格线）→ 吸附到最近的墙锚点，画出幽灵墙预览
  （绿色=可放，红色=不可放），点一下即落墙；
* 鼠标移到**格子中心** → 高亮合法落点，点一下即走子（含跳跃）。

两者由"鼠标离最近网格线的距离"自动区分：离网格线近就是放墙，离格子中心近就是走子，
所以不需要额外按钮来切换模式 —— 也就不存在"放墙按钮"和"走子按钮"的冲突。
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
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

#: 鼠标离网格线多近算"在格子边缘"（单位：格；0.5 就是半个格子）
EDGE_ZONE = 0.26
#: 到两条网格线的距离差小于这个值时，优先给**能放**的那一种朝向
ORIENTATION_TIE = 0.10


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
    # 悬停意图：格子边缘 = 放墙，格子中心 = 走子
    # ------------------------------------------------------------------ #

    def _intent(self, pos: tuple[int, int], game, state: QuoridorState) -> _Intent:
        if not isinstance(state, QuoridorState):
            return _Intent("none")
        size = state.size
        fx, fy = self._fractional(pos)
        if not (-0.3 <= fx <= size + 0.3 and -0.3 <= fy <= size + 0.3):
            return _Intent("none")

        line_x = _round_half_up(fx)
        line_y = _round_half_up(fy)
        dist_v = abs(fx - line_x)  # 到竖直网格线的距离
        dist_h = abs(fy - line_y)  # 到水平网格线的距离

        # 只有**内部**网格交点附近才能放墙（棋盘外框上没有墙槽）
        interior = 1 <= line_x <= size - 1 and 1 <= line_y <= size - 1
        if interior and min(dist_v, dist_h) <= EDGE_ZONE:
            ax, ay = line_x - 1, line_y - 1
            wall_h = (HORIZONTAL, ax, ay)
            wall_v = (VERTICAL, ax, ay)
            if dist_h <= dist_v:
                first, second = wall_h, wall_v
            else:
                first, second = wall_v, wall_h
            first_legal = game.is_wall_legal(state, state.current_player, first)
            second_legal = game.is_wall_legal(state, state.current_player, second)
            # 离两条线一样近（角落）时，优先给出能放的那一种
            if first_legal or not second_legal or abs(dist_h - dist_v) > ORIENTATION_TIE:
                chosen, legal = first, first_legal
            else:
                chosen, legal = second, second_legal
            return _Intent("wall", self.cell_at(pos), chosen, legal)

        cell = self.cell_at(pos)
        if cell is None:
            return _Intent("none")
        return _Intent("cell", cell, None, cell in self._targets(game, state))

    def _refresh_intent(self, pos, game, state, view: ViewState) -> _Intent:
        intent = self._intent(pos, game, state)
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
        self._refresh_intent(pos, game, state, view)

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, QuoridorState):
            return None
        intent = self._refresh_intent(pos, game, state, view)
        player = state.current_player
        targets = self._targets(game, state)

        if intent.kind == "wall" and intent.wall is not None:
            if intent.legal:
                return WallMove(*intent.wall)
            # 该位置放不了墙时，退一步：鼠标底下的格子若是合法落点就走子
            if intent.cell is not None and intent.cell in targets:
                return PawnMove(state.pawns[player], intent.cell)
            return None

        if intent.cell is not None and intent.cell in targets:
            return PawnMove(state.pawns[player], intent.cell)
        return None

    def hover_hint(self) -> tuple[str, tuple[int, int, int]]:
        """给棋盘 HUD 用的一句话提示。"""
        if self._hover_wall is not None:
            kind = "横墙" if self._hover_wall[0] == HORIZONTAL else "竖墙"
            if self._hover_legal:
                return f"点击放置{kind}", theme.OK
            return f"{kind}不可放", theme.BAD
        if self._hover_target is not None:
            return "点击走子", theme.ACCENT
        return "", theme.TEXT_FAINT

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

        self._draw_goal_rows(surface, board, state)
        self._draw_cells(surface, state)
        self._draw_slots(surface, state)
        self._draw_walls(surface, state)
        if interactive:
            self._draw_ghost(surface)
        self._draw_last_move(surface, state)
        if interactive:
            self._draw_hints(surface, state, game)
        self._draw_pawns(surface, state, interactive)
        render.rounded_rect(surface, board.inflate(6, 6), theme.BORDER, theme.RADIUS, width=1)

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


__all__ = ["QuoridorView", "make_view"]
