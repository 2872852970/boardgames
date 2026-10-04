"""点格棋的棋盘渲染与交互。

**只用鼠标**：鼠标移到两个相邻点之间的格线上会高亮预览，点击即画边；
画上就能占格的"封口边"再加一圈白描边提示。

鼠标 → 边 的换算
----------------
把整块棋盘按"离哪条边最近"切开（每条边是一个线段，算**欧氏距离**），
鼠标落在哪一格区域的边界最近，就命中哪条边：

* 棋盘内**处处**都能命中，没有"点在格子正中间什么都没反应"的死区
  （死区会让玩家以为鼠标和线差了半格 —— 明明指着线，亮的是旁边那条）；
* 命中的一定是**几何上最近**的那条边，绝不会出现"鼠标在左边、高亮线画到右边"；
* 未画的边会画成**浅色格线**（:meth:`_draw_slots`），高亮落在哪条线上
  一眼可见，不用靠猜。
"""

from __future__ import annotations

import math

import pygame

from boardgames.core.move import Move
from boardgames.games.dotsboxes import heuristic as heu
from boardgames.games.dotsboxes.move import EdgeMove
from boardgames.games.dotsboxes.state import DotsBoxesState
from boardgames.ui import render, theme
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

#: 棋盘上圆点的半径
_DOT_RADIUS = 4
#: 已画的边的粗度
_EDGE_THICK = 5
#: 未画的边的"格线轨道"粗度（比真线细，低调）
_SLOT_THICK = 3
#: 悬停预览比真线略粗
_GHOST_THICK = _EDGE_THICK + 2


def _half_up(value: float) -> int:
    """四舍五入（.5 向上）。

    用 ``math.floor(v + 0.5)`` 而不是内置 ``round()`` —— 后者是"银行家舍入"，
    在 .5 处会往偶数取整，鼠标扫过整格边界时选中的边会跳来跳去
    （昆虫棋的坐标换算踩过同一个坑）。
    """
    return math.floor(value + 0.5)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class DotsBoxesView:
    """点格棋的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 600)
        self.cell = 56
        self.origin = (0, 0)
        self.size = 6
        self._hover: EdgeMove | None = None
        self._last_move: Move | None = None
        #: 本次悬停命中的边（``(orient, row, col)``），用于"多宽算多宽"的提示
        self._hover_edge: tuple[int, int, int] | None = None

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        span = min(area.width, area.height)
        cell = int(span / (self.size + 1.0))
        self.cell = max(20, cell)
        board_w = self.cell * (self.size - 1)
        board_h = self.cell * (self.size - 1)
        self.origin = (
            area.x + (area.width - board_w) // 2,
            area.y + (area.height - board_h) // 2,
        )

    def set_size(self, size: int) -> None:
        self.size = size
        self.layout(self.area)

    def point_pos(self, row: int, col: int) -> tuple[int, int]:
        return (
            self.origin[0] + col * self.cell,
            self.origin[1] + row * self.cell,
        )

    def board_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.origin[0],
            self.origin[1],
            self.cell * (self.size - 1),
            self.cell * (self.size - 1),
        )

    # ------------------------------------------------------------------ #
    # 命中测试
    # ------------------------------------------------------------------ #

    @staticmethod
    def _segment_distance(
        gx: float, gy: float, orient: int, row: int, col: int
    ) -> float:
        """鼠标（格坐标）到某条边的线段的**欧氏距离**（单位 = 格）。"""
        if orient == 0:  # 水平边：y = row，x ∈ [col, col+1]
            perp = gy - row
            along = gx - min(max(gx, col), col + 1)
        else:  # 垂直边：x = col，y ∈ [row, row+1]
            perp = gx - col
            along = gy - min(max(gy, row), row + 1)
        return math.hypot(perp, along)

    def _edge_at(self, pos: tuple[int, int]) -> tuple[int, int, int] | None:
        """像素位置 → **离鼠标最近**那条边的 ``(orient, row, col)``。

        全棋盘（含半格余量）切分成"最近边"的 Voronoi 区域，所以：

        * 棋盘内任何一点都能命中，不存在"看着就在线上、却什么都没亮"的死区；
        * 命中的边一定是几何最近的 —— 不存在差半格、错一格的错位；
        * 只算两条候选（最近的水平边 / 最近的垂直边）就够了：水平边的垂直距离
          只跟行有关、沿边距离只跟列有关，两边各自取最近即可，不必枚举全部边。
        """
        cell = self.cell
        n = self.size
        if cell <= 0 or n < 2:
            return None
        gx = (pos[0] - self.origin[0]) / cell
        gy = (pos[1] - self.origin[1]) / cell
        # 棋盘外留半格余量：贴着棋盘边缘点也不至于"没反应"
        if not (-0.5 <= gx <= n - 0.5) or not (-0.5 <= gy <= n - 0.5):
            return None

        h_row = _clamp(_half_up(gy), 0, n - 1)
        h_col = _clamp(math.floor(gx), 0, n - 2)
        v_col = _clamp(_half_up(gx), 0, n - 1)
        v_row = _clamp(math.floor(gy), 0, n - 2)

        d_h = self._segment_distance(gx, gy, 0, h_row, h_col)
        d_v = self._segment_distance(gx, gy, 1, v_row, v_col)
        # 一样近（正落在交点/正中间）时取水平边，保证结果确定、不抖
        if d_h <= d_v:
            return (0, h_row, h_col)
        return (1, v_row, v_col)

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #

    def handle_motion(self, pos, game, state, view: ViewState) -> None:
        view.mouse = pos
        if not isinstance(state, DotsBoxesState) or state.is_terminal():
            self._clear_hover()
            return
        found = self._edge_at(pos)
        if found is None:
            self._clear_hover()
            return
        orient, row, col = found
        # **必须用 ``state.current`` 造着法**：``Game.is_legal`` 会校验
        # ``move.player == state.current``，写死 0 会让"轮到玩家 2"时预览永远不亮。
        move = EdgeMove(orient, row, col, state.current)
        if game.is_legal(state, move):
            self._hover = move
            self._hover_edge = found
        else:
            self._clear_hover()

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, DotsBoxesState) or state.is_terminal():
            return None
        found = self._edge_at(pos)
        if found is None:
            return None
        orient, row, col = found
        move = EdgeMove(orient, row, col, state.current)
        if not game.is_legal(state, move):
            return None
        return move

    def _clear_hover(self) -> None:
        self._hover = None
        self._hover_edge = None

    def clear_hover(self) -> None:
        """鼠标离开棋盘时由场景调用：别把上一条幽灵线留在画面上。

        可选钩子（``hasattr`` 探测），场景不认识它的棋类一无所知。
        """
        self._clear_hover()

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        if self._hover is None:
            return "把鼠标移到两个点之间的格线上", theme.TEXT_FAINT
        direction = "横" if self._hover.orient == 0 else "竖"
        # 提示文字颜色用当前玩家色（与落下的边一致）
        color = theme.PLAYER_COLORS[self._hover.player]
        return f"点击画{direction}边", color

    def idle_hint(self) -> str:
        """鼠标不在任何边上时，左上角胶囊显示什么。"""
        return "移到两点之间的格线上，点击画边"

    def hud_hint(self, *, wall_mode: bool = False, paused: bool = False) -> str:
        if paused:
            return "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        return "在相邻两点间画边，画满一格即占为己有并再走一手 · 格子多者胜"

    def in_placement_mode(self) -> bool:
        return False

    # ------------------------------------------------------------------ #
    # 动画（点格棋落边即时呈现，无动画）
    # ------------------------------------------------------------------ #

    def animate(self, move: Move, duration_ms: int) -> None:
        pass

    def update(self, dt_ms: float) -> bool:
        return False

    def is_animating(self) -> bool:
        return False

    def reset(self) -> None:
        self._clear_hover()
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
        state: DotsBoxesState,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        if state.size != self.size:
            self.set_size(state.size)

        board = self.board_rect()
        render.panel(surface, board.inflate(16, 16), color=theme.BOARD_BG, radius=theme.RADIUS + 6)

        self._draw_boxes(surface, state)
        if view.extra.get("show_hints", True):
            self._draw_slots(surface, state)
        self._draw_edges(surface, state)
        if interactive and self._hover is not None:
            self._draw_ghost(surface, state)
        self._draw_points(surface, state)

    def _edge_segment(self, orient: int, row: int, col: int) -> tuple[tuple[int, int], tuple[int, int]]:
        if orient == 0:
            a = self.point_pos(row, col)
            b = self.point_pos(row, col + 1)
        else:
            a = self.point_pos(row, col)
            b = self.point_pos(row + 1, col)
        return a, b

    def _undrawn_edges(self, state: DotsBoxesState):
        """所有还没画的边（画成浅色格线，让"哪里能画"一眼可见）。"""
        for i, drawn in enumerate(state.h_edges):
            if not drawn:
                yield (0, *divmod(i, state.size - 1))
        for i, drawn in enumerate(state.v_edges):
            if not drawn:
                yield (1, *divmod(i, state.size))

    def _draw_slots(self, surface, state: DotsBoxesState) -> None:
        color = theme.mix(theme.BOARD_BG, theme.BORDER, 0.5)
        for orient, row, col in self._undrawn_edges(state):
            a, b = self._edge_segment(orient, row, col)
            pygame.draw.line(surface, color, a, b, _SLOT_THICK)

    def _draw_edges(self, surface, state: DotsBoxesState) -> None:
        for i, owner in enumerate(state.h_edges):
            if not owner:
                continue
            row, col = divmod(i, state.size - 1)
            a, b = self._edge_segment(0, row, col)
            pygame.draw.line(surface, theme.PLAYER_COLORS[owner - 1], a, b, _EDGE_THICK)
        for i, owner in enumerate(state.v_edges):
            if not owner:
                continue
            row, col = divmod(i, state.size)
            a, b = self._edge_segment(1, row, col)
            pygame.draw.line(surface, theme.PLAYER_COLORS[owner - 1], a, b, _EDGE_THICK)

    def _draw_boxes(self, surface, state: DotsBoxesState) -> None:
        grid = state.size - 1
        for row in range(grid):
            for col in range(grid):
                owner = state.box_owner(row, col)
                if owner == 0:
                    continue
                player = owner - 1
                x = self.origin[0] + col * self.cell
                y = self.origin[1] + row * self.cell
                color = theme.PLAYER_COLORS[player]
                layer = pygame.Surface((self.cell, self.cell), pygame.SRCALPHA)
                pygame.draw.rect(layer, (*color, 60), layer.get_rect())
                surface.blit(layer, (x, y))

    def _draw_points(self, surface, state: DotsBoxesState) -> None:
        r = _DOT_RADIUS
        for row in range(state.size):
            for col in range(state.size):
                pygame.draw.circle(surface, theme.TEXT_DIM, self.point_pos(row, col), r)

    def _draw_ghost(self, surface, state: DotsBoxesState) -> None:
        """悬停预览：用**当前玩家色**高亮这条边（封口边加亮一圈）。"""
        hover = self._hover
        if hover is None:
            return
        a, b = self._edge_segment(hover.orient, hover.row, hover.col)
        # 预览颜色 = 当前玩家色（琥珀/蓝），与落下后的边颜色一致，不会"提示蓝、落下黄"
        color = theme.PLAYER_COLORS[hover.player]
        closing = heu.boxes_closed_by_move(state, hover.orient, hover.row, hover.col)
        if closing:
            # 封口边：加一圈白色描边提示"这一步能占格"
            pygame.draw.line(surface, theme.SELECT_RING, a, b, _GHOST_THICK + 4)
        pygame.draw.line(surface, color, a, b, _GHOST_THICK)


def make_view() -> DotsBoxesView:
    return DotsBoxesView()


__all__ = ["DotsBoxesView", "make_view"]
