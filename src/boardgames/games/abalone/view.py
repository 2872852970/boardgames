"""大力士棋的棋盘渲染与交互（六边形）。

坐标系
------
**pointy-top 六边形 + axial ``(q, r)``**，换算全在
:mod:`~boardgames.games.abalone.geometry` 里（纯数学，不碰 pygame），本模块只管像素。

* ``self.cell`` = 六边形外接圆半径 ``size``；``self.origin`` = 包围盒左上角。
  这两个**属性名不能改** —— ``tests/ui/helpers.py:pos_for()`` 依赖它们。
* 格子中心 = ``包围盒中心 + axial_to_pixel(pos, size)``，**只有一处**做这一步换算。
* 命中测试 ``pos_at()`` 用 cube round，并且**必须**再校验一次是否在盘内：
  ``MatchScene`` 用未内缩的 ``board_area`` 做 ``collidepoint``，视图一定会收到
  棋盘外的坐标。

交互：两段式点击
----------------
1. 点一枚己方棋子 —— 选中它（1 子组），并画出该组所有合法着法的**目标格**；
2. 再点一枚与选中组共线且连续的己方棋子 —— 扩成 2 / 3 子组；
3. 点任意一个目标格 —— 出招。

提示**画在目标格上**（整格 ≈ 48px 的热区），而不是在选中组周围画六个小三角：
小三角热区只有十几像素，还常常被相邻的己方棋子压住，点不中。

**必须实现** :meth:`in_placement_mode` 并返回 ``False`` —— 否则 ``MatchScene``
会认为本视图"支持放墙模式"，玩家右键进模式后按 V 键会调用并不存在的
``flip_orientation()`` 而崩溃。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame
import pygame.gfxdraw

from boardgames.core.move import Move
from boardgames.games.abalone.geometry import (
    BOARD_UNIT_H,
    BOARD_UNIT_W,
    CELLS,
    DIRECTIONS,
    INDEX,
    Pos,
    axial_to_pixel,
    direction_pixel,
    group_axis,
    hex_points,
    on_board,
    pixel_to_axial,
)
from boardgames.games.abalone.move import AbaloneMove
from boardgames.games.abalone.state import AbaloneState
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

#: 棋子半径 / 六边形外接圆半径（六边形内切圆半径是 0.866，留一点缝隙）
MARBLE_RATIO = 0.78
#: 格子六边形画得比实际格距小一点，留出网格线
CELL_SHRINK = 0.96
#: 目标格提示的圆盘半径 / cell
TARGET_RATIO = 0.46

#: 目标格提示的三种语义（普通 / 推动 / 挤出盘外）
KIND_COLORS = (theme.OK, theme.ACCENT, theme.BAD)


@dataclass
class _SlideAnim:
    """整组（含被推的对手子）沿方向滑行一格。"""

    move: AbaloneMove
    tween: Tween


class AbaloneView:
    """大力士棋的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 600)
        self.cell = 48
        self.origin = (0, 0)
        self._center = (0.0, 0.0)
        self._anim: _SlideAnim | None = None
        self._last_move: Move | None = None
        #: 当前选中的己方棋子（按 (q, r) 排序）
        self._selected: tuple[Pos, ...] | None = None
        #: 选中状态所属的局面对象（换了对象就清空 —— 落子 / 悔棋 / 新局都算）
        self._selected_state: AbaloneState | None = None
        #: 目标格 -> (着法, 语义)；点哪一格就走哪一步
        self._targets: dict[Pos, tuple[AbaloneMove, int]] = {}
        self._hover: Pos | None = None

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        """按可用区域重算六边形尺寸与原点。

        ``origin`` / ``cell`` 这两个属性名是 UI 测试的 ``pos_for()`` 依赖的，
        不要改名。
        """
        self.area = pygame.Rect(area)
        # 棋盘包围盒：宽 9√3 * size、高 14 * size（见 geometry.BOARD_UNIT_*）
        size = int(min(area.width / BOARD_UNIT_W, area.height / BOARD_UNIT_H))
        self.cell = max(10, size - 1)  # 留 1px 安全边
        width = BOARD_UNIT_W * self.cell
        height = BOARD_UNIT_H * self.cell
        left = area.x + (area.width - width) / 2
        top = area.y + (area.height - height) / 2
        self.origin = (int(left), int(top))
        self._center = (left + width / 2, top + height / 2)

    def board_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.origin[0],
            self.origin[1],
            int(BOARD_UNIT_W * self.cell),
            int(BOARD_UNIT_H * self.cell),
        )

    def cell_center(self, pos: Pos) -> tuple[int, int]:
        """格坐标（**局面坐标**）→ 屏幕像素中心。"""
        x, y = axial_to_pixel(pos, self.cell)
        return (int(self._center[0] + x), int(self._center[1] + y))

    def pos_at(self, xy: tuple[int, int]) -> Pos | None:
        """像素 → 格坐标；棋盘外返回 ``None``。"""
        pos = pixel_to_axial(xy[0] - self._center[0], xy[1] - self._center[1], self.cell)
        return pos if on_board(*pos) else None

    @property
    def marble_radius(self) -> int:
        return max(3, int(self.cell * MARBLE_RATIO))

    def hex_at(self, pos: Pos, scale: float = CELL_SHRINK) -> list[tuple[float, float]]:
        """画一个格子用的六边形顶点（比格距略小，网格线就出来了）。"""
        return hex_points(self.cell_center(pos), self.cell * scale)

    # ------------------------------------------------------------------ #
    # 交互（两段式点击）
    # ------------------------------------------------------------------ #

    def _sync_state(self, state) -> None:
        """局面对象换了就清空选择（落子 / 悔棋 / 新局都会换对象）。"""
        if self._selected_state is not state:
            self._selected_state = state
            self._selected = None
            self._targets = {}

    def _select(self, game, state: AbaloneState, cells: tuple[Pos, ...]) -> None:
        self._selected = tuple(sorted(cells))
        self._selected_state = state
        self._targets = {}
        for move in game.legal_moves(state):
            if move.cells != self._selected:
                continue
            dest = self._target_cell(move)
            if dest is None:
                continue
            kind = 2 if move.ejected is not None else (1 if move.pushed else 0)
            # 两个方向理论上可能算出同一个目标格；先到先得，绝不覆盖
            self._targets.setdefault(dest, (move, kind))

    def _target_cell(self, move: AbaloneMove) -> Pos | None:
        """这一手"点哪儿"的目标格 = 组里**最前面那一枚**的落点。

        横移时六枚成员的前后不好定义，就取组内下标最小的那一枚 —— 关键是
        六个方向算出来的目标格互不相同，点哪格对应哪一手不会有歧义。
        """
        members = set(move.cells)
        head = None
        for pos in move.cells:
            dq, dr = _DELTA[move.direction]
            if (pos[0] + dq, pos[1] + dr) not in members:
                head = pos
                break
        if head is None:
            head = move.cells[0]
        dq, dr = _DELTA[move.direction]
        dest = (head[0] + dq, head[1] + dr)
        return dest if dest in INDEX else None

    def handle_motion(self, pos, game, state, view: ViewState) -> None:
        view.mouse = pos
        if not isinstance(state, AbaloneState):
            self._hover = None
            return
        self._sync_state(state)
        self._hover = self.pos_at(pos)

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, AbaloneState) or state.is_terminal():
            self._selected = None
            self._targets = {}
            return None
        self._sync_state(state)
        cell = self.pos_at(pos)
        if cell is None:
            self._selected = None
            self._targets = {}
            return None

        # 1) 点在目标格上 -> 出招
        if cell in self._targets:
            move = self._targets[cell][0]
            self._selected = None
            self._targets = {}
            return move

        # 2) 点己方棋子 -> 选组 / 扩组
        if state.at(cell) == state.current + 1:
            if self._selected is None:
                self._select(game, state, (cell,))
                return None
            if cell in self._selected:
                if len(self._selected) == 1:
                    self._selected = None
                    self._targets = {}
                else:
                    rest = tuple(p for p in self._selected if p != cell)
                    # 只能从端点拿掉，抽掉中间一枚会破坏连续性
                    if len(rest) == 1 or group_axis(tuple(INDEX[p] for p in rest)) >= 0:
                        self._select(game, state, rest)
                return None
            merged = tuple(sorted(self._selected + (cell,)))
            if len(merged) <= 3 and group_axis(tuple(INDEX[p] for p in merged)) >= 0:
                self._select(game, state, merged)
            else:
                self._select(game, state, (cell,))  # 不共线 -> 以它重新起组
            return None

        # 3) 点别处 -> 取消选择
        self._selected = None
        self._targets = {}
        return None

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        """棋盘左上角提示胶囊里的一句话。"""
        hit = self._targets.get(self._hover) if self._hover is not None else None
        if hit is not None:
            move, kind = hit
            return move.describe(), KIND_COLORS[kind]
        if self._selected is None:
            return "点击一枚己方棋子选中它", theme.TEXT_FAINT
        if not self._targets:
            return "这一组无处可走，换一组", theme.BAD
        return "点虚线目标格走子，或再点同线己方子扩组", theme.ACCENT

    def hud_hint(self, *, wall_mode: bool = False, paused: bool = False) -> str:
        if paused:
            return "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        return "点己方棋子选组（1~3 连子），再点目标格走子 · 以多推少把对手挤出盘外"

    def in_placement_mode(self) -> bool:
        """大力士棋没有"放置模式"。

        **必须实现**：``MatchScene._place_mode_supported()`` 用 ``hasattr`` 探测，
        缺了这个方法的视图会被当成"支持放墙模式"，右键进模式后按 V 键会崩。
        """
        return False

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #

    def animate(self, move: Move, duration_ms: int) -> None:
        if duration_ms <= 0 or not isinstance(move, AbaloneMove):
            return
        # 刻意**不排队**：AI 双方连续走子时排队会累积延迟
        self._anim = _SlideAnim(move, Tween(duration_ms / 1000.0))

    def update(self, dt_ms: float) -> bool:
        if self._anim is None:
            return False
        if self._anim.tween.update(dt_ms / 1000.0):  # Tween.update 返回"是否已结束"
            self._anim = None
            return False
        return True

    def is_animating(self) -> bool:
        return self._anim is not None

    def reset(self) -> None:
        self._anim = None
        self._last_move = None
        self._selected = None
        self._selected_state = None
        self._targets = {}
        self._hover = None

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
        state: AbaloneState,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        self._sync_state(state)
        board = self.board_rect()
        render.panel(surface, board.inflate(16, 16), color=theme.BOARD_BG, radius=theme.RADIUS + 6)

        self._draw_cells(surface)
        self._draw_marbles(surface, state, interactive)
        if interactive:
            # 提示必须画在棋子**之上**：推挤型着法的目标格本身就是对手棋子所在的
            # 那格，先画就会被棋子整个盖掉，看着像"这手不能走"。
            self._draw_targets(surface, state)
            self._draw_selection(surface)

    def _draw_cells(self, surface: pygame.Surface) -> None:
        """61 个格子。用 3-着色（``(q - r) % 3``）—— 六边形网格的相邻格
        不可能只用两种颜色区分开。"""
        for q, r in CELLS:
            points = self.hex_at((q, r))
            bucket = (q - r) % 3
            if bucket == 0:
                color = theme.CELL
            elif bucket == 1:
                color = theme.CELL_ALT
            else:
                color = theme.mix(theme.CELL, theme.CELL_ALT, 0.5)
            pygame.gfxdraw.filled_polygon(surface, _int_points(points), color)

    def _draw_targets(self, surface: pygame.Surface, state: AbaloneState) -> None:
        for dest, (move, kind) in self._targets.items():
            self._draw_target(surface, dest, move, kind, state.at(dest) != 0)

    def _draw_target(
        self,
        surface: pygame.Surface,
        dest: Pos,
        move: AbaloneMove,
        kind: int,
        occupied: bool,
    ) -> None:
        color = KIND_COLORS[kind]
        center = self.cell_center(dest)
        radius = max(4, int(self.cell * TARGET_RATIO))
        layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        if not occupied:
            pygame.draw.circle(layer, (*color, 70), (radius, radius), radius)
        pygame.draw.circle(
            layer, (*color, 240 if occupied else 210), (radius, radius), radius, 3 if occupied else 2
        )
        surface.blit(layer, (center[0] - radius, center[1] - radius))

        dx, dy = direction_pixel(move.direction, self.cell)
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        tip = (center[0] + ux * radius * 0.66, center[1] + uy * radius * 0.66)
        base = (tip[0] - ux * radius * 0.36, tip[1] - uy * radius * 0.36)
        px, py = -uy, ux
        wing = radius * 0.30
        pygame.draw.polygon(
            surface,
            color,
            [tip, (base[0] + px * wing, base[1] + py * wing), (base[0] - px * wing, base[1] - py * wing)],
        )

    def _draw_selection(self, surface: pygame.Surface) -> None:
        if not self._selected:
            return
        radius = self.marble_radius
        for pos in self._selected:
            pygame.draw.circle(surface, theme.SELECT_RING, self.cell_center(pos), radius + 3, 2)

    def _draw_marbles(self, surface: pygame.Surface, state: AbaloneState, interactive: bool) -> None:
        """画 28 枚棋子。

        正在位移的那一组**最后画**：它们从上一格滑过来，先画会被沿途静止的
        棋子盖住。被挤出盘外的那一枚已经不在 ``state.cells`` 里了，单独画并淡出。
        """
        anim = self._anim
        step = (0.0, 0.0)
        progress = 1.0
        moving: frozenset[Pos] = frozenset()
        if anim is not None:
            step = direction_pixel(anim.move.direction, self.cell)
            progress = anim.tween.eased()
            moving = frozenset(anim.move.destinations())

        last = self._last_move if isinstance(self._last_move, AbaloneMove) else None
        last_cells = frozenset(last.destinations()) if last is not None else frozenset()

        deferred: list[tuple[tuple[float, float], int]] = []
        for index, value in enumerate(state.cells):
            if not value:
                continue
            pos = CELLS[index]
            player = value - 1
            center = self.cell_center(pos)
            if pos in moving:
                deferred.append(
                    ((center[0] + (progress - 1.0) * step[0], center[1] + (progress - 1.0) * step[1]),
                     player)
                )
                continue
            self._draw_marble(
                surface, center, player, active=interactive and pos in last_cells
            )
        for center, player in deferred:
            self._draw_marble(surface, center, player, active=True)

        if anim is not None and anim.move.ejected is not None:
            center = self.cell_center(anim.move.ejected)
            alpha = int(255 * max(0.0, min(1.0, 2.0 * (1.0 - progress))))
            if alpha > 4:
                self._draw_marble(
                    surface,
                    (center[0] + progress * step[0], center[1] + progress * step[1]),
                    1 - anim.move.player,
                    alpha=alpha,
                )

    def _draw_marble(
        self,
        surface: pygame.Surface,
        center: tuple[float, float],
        player: int,
        *,
        active: bool = False,
        alpha: int = 255,
    ) -> None:
        """一枚棋子：暗边 → 主体 → 高光。索引一律是**玩家号 0/1**。"""
        radius = self.marble_radius
        cx, cy = int(center[0]), int(center[1])
        color = theme.PLAYER_COLORS[player]
        dark = theme.PLAYER_DARK[player]
        if alpha >= 255:
            if active:
                render.circle_glow(surface, (cx, cy), radius, color, layers=4, max_alpha=90)
            pygame.draw.circle(surface, dark, (cx, cy), radius)
            pygame.draw.circle(surface, color, (cx, cy), max(2, radius - max(1, radius // 12)))
            pygame.draw.circle(
                surface,
                theme.lighten(color, 0.40),
                (cx - radius // 3, cy - radius // 3),
                max(2, radius // 3),
            )
            if active:
                pygame.draw.circle(surface, theme.SELECT_RING, (cx, cy), radius + 3, 2)
            return
        layer = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        mid = radius + 1
        pygame.draw.circle(layer, (*dark, alpha), (mid, mid), radius)
        pygame.draw.circle(layer, (*color, alpha), (mid, mid), max(2, radius - max(1, radius // 12)))
        surface.blit(layer, (cx - mid, cy - mid))


#: 六个方向的 axial 增量（视图里只用来算"这一组的落点是哪一格"）
_DELTA: tuple[Pos, ...] = DIRECTIONS


def _int_points(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(int(round(x)), int(round(y))) for x, y in points]


def make_view() -> AbaloneView:
    """视图工厂（注册表用）。"""
    return AbaloneView()


__all__ = ["AbaloneView", "make_view"]
