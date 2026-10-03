"""重力四子棋的棋盘渲染与交互。

**只用鼠标**：移动到某一列就预览棋子会落到哪一格，点击即投子。

**行号是反的**：局面（:class:`Connect4State`）里 ``row == 0`` 是**最底行**，
重力把人往 0 压；屏幕 y 却向下增大。翻转只在 :meth:`Connect4View.screen_row`
一处做，其它地方一律用局面坐标 —— 两处各翻一次就等于没翻，
表现出来就是"棋子全堆在棋盘顶部"（曾经就是这么错的）。

落子动画走 :class:`~boardgames.ui.animation.BounceTween` ——
自由落体 → 触底回弹 → 阻尼衰减，是真的积分运动方程而不是插值曲线。
所有棋子都从棋盘上沿之上同一高度进场，落点越低掉得越远；
只给**最后一手**的那枚棋子加纵向偏移，其余棋子静止不动。
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from boardgames.core.move import Move
from boardgames.games.connect4.move import DropMove
from boardgames.games.connect4.state import Connect4State
from boardgames.ui import render, theme
from boardgames.ui.animation import BounceTween
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

#: 棋子进入画面的高度：**棋盘上沿之上**多少格（所有棋子都从这个高度掉下来，
#: 落点越低掉得越远）。不能从 0 开始 —— 否则第一帧看起来像"棋子凭空出现"。
DROP_ENTRY_CELLS = 0.25
#: 空格圆窝的直径占格子的比例
SOCKET_RATIO = 0.86


@dataclass
class _DropAnim:
    move: DropMove
    tween: BounceTween


class Connect4View:
    """重力四子棋的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 600)
        self.cell = 56
        self.origin = (0, 0)
        self.cols = 7
        self.rows = 6
        self._anim: _DropAnim | None = None
        self._last_move: Move | None = None
        self._hover_col: int | None = None
        self._hover_state: Connect4State | None = None
        self._open_cols: tuple[int, ...] = ()
        #: 终局时高亮的胜利四子
        self._win_line: tuple[tuple[int, int], ...] | None = None

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        """按可用区域重算格子尺寸与原点。

        ``origin`` / ``cell`` 这两个属性名是 UI 测试的 ``pos_for()`` 依赖的，
        不要改名。
        """
        self.area = pygame.Rect(area)
        span = min(area.width, area.height)
        # 棋盘上下各留一点余量（落子动画要能从上方飞入）
        cell = int(span / (max(self.cols, self.rows) + 0.9))
        self.cell = max(16, cell)
        board_w = self.cell * self.cols
        board_h = self.cell * self.rows
        self.origin = (
            area.x + (area.width - board_w) // 2,
            area.y + (area.height - board_h) // 2,
        )

    def set_size(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.layout(self.area)

    def screen_row(self, row: int) -> int:
        """局面行号 → 屏幕行号（自上而下 0..rows-1）。

        **坐标是反的**：局面里 ``row == 0`` 是最底行（重力把人往 0 压），
        而屏幕 y 向下增大。整个视图只能在这一处翻转，别在别处再翻一次。
        """
        return self.rows - 1 - row

    def cell_center(self, col: int, row: int) -> tuple[int, int]:
        """棋格 ``(col, row)``（**局面坐标**）的屏幕中心。"""
        return (
            self.origin[0] + int((col + 0.5) * self.cell),
            self.origin[1] + int((self.screen_row(row) + 0.5) * self.cell),
        )

    def board_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.origin[0], self.origin[1], self.cell * self.cols, self.cell * self.rows
        )

    @property
    def socket_radius(self) -> int:
        return max(3, int(self.cell * SOCKET_RATIO / 2))

    def col_at(self, pos: tuple[int, int]) -> int | None:
        """像素 → 列号。整列都是合法点击区（不用精确对准圆窝）。"""
        x = pos[0] - self.origin[0]
        if not (0 <= x < self.cell * self.cols):
            return None
        return min(self.cols - 1, x // self.cell)

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #

    def _legal_columns(self, state: Connect4State) -> tuple[int, ...]:
        if self._hover_state is not state:
            self._hover_state = state
            self._open_cols = tuple(
                c for c in range(state.cols) if state.heights[c] < state.rows
            )
        return self._open_cols

    def handle_motion(self, pos, game, state, view: ViewState) -> None:
        view.mouse = pos
        if not isinstance(state, Connect4State) or state.is_terminal():
            self._hover_col = None
            return
        col = self.col_at(pos)
        self._hover_col = col if col in self._legal_columns(state) else None

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, Connect4State) or state.is_terminal():
            return None
        col = self.col_at(pos)
        if col is None or col not in self._legal_columns(state):
            return None
        return DropMove(col, state.heights[col], state.current)

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        """给棋盘 HUD 用的一句话提示。"""
        if self._hover_col is None:
            return "把鼠标移到某一列", theme.TEXT_FAINT
        row = None
        if isinstance(self._hover_state, Connect4State):
            row = self._hover_state.heights[self._hover_col]
        return f"点击第 {self._hover_col + 1} 列（落在第 {row + 1} 层）", theme.ACCENT

    def hud_hint(self, *, wall_mode: bool = False, paused: bool = False) -> str:
        """棋盘底部的操作提示。四子棋没有放墙模式，右键也没用。"""
        if paused:
            return "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        return "把鼠标移到某一列会预览落点，点击投子 · 横竖斜连成四子即胜"

    def in_placement_mode(self) -> bool:
        """四子棋没有"放置模式"，永远为 False。"""
        return False

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #

    def drop_px_for(self, row: int) -> float:
        """从棋盘上沿掉到第 ``row`` 行需要走多少像素。

        所有棋子都从**同一个高度**（棋盘上沿往上 ``DROP_ENTRY_CELLS`` 格）进场，
        所以落点越低（``row`` 越小）掉得越远 —— 和真棋具从顶口投子一致。
        """
        screen_row = max(0, self.screen_row(row))
        return self.cell * (screen_row + 0.5 + DROP_ENTRY_CELLS)

    def animate(self, move: Move, duration_ms: int) -> None:
        if duration_ms <= 0 or not isinstance(move, DropMove):
            return
        drop_px = self.drop_px_for(move.row)
        # 刻意**不排队**：已有动画在播就直接结算掉再起新的。
        # AI 双方连续落子时排队会累积延迟，观感反而更差。
        self._anim = _DropAnim(move, BounceTween(drop_px=drop_px, duration_s=duration_ms / 1000))

    def update(self, dt_ms: float) -> bool:
        if self._anim is None:
            return False
        if self._anim.tween.update(dt_ms / 1000.0):
            return True
        self._anim = None
        return False

    def is_animating(self) -> bool:
        return self._anim is not None

    def reset(self) -> None:
        self._anim = None
        self._last_move = None
        self._hover_col = None
        self._hover_state = None
        self._win_line = None

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
        state: Connect4State,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        if state.cols != self.cols or state.rows != self.rows:
            self.set_size(state.cols, state.rows)

        # 局面变了（落子 / 悔棋 / 新局）就重算可投列与终局胜线
        if self._hover_state is not state:
            self._legal_columns(state)
            self._win_line = state.winning_line() if state.is_terminal() else None

        board = self.board_rect()
        render.panel(surface, board.inflate(12, 12), color=theme.BOARD_BG, radius=theme.RADIUS + 6)

        self._draw_sockets(surface, state)
        if self._win_line:
            self._draw_win_line(surface, state)
        if interactive:
            self._draw_ghost(surface, state)
        self._draw_discs(surface, state)

    def _draw_sockets(self, surface, state: Connect4State) -> None:
        """空格的圆窝。"""
        radius = self.socket_radius
        for row in range(state.rows):
            for col in range(state.cols):
                center = self.cell_center(col, row)
                color = theme.CELL if (row + col) % 2 == 0 else theme.CELL_ALT
                pygame.draw.circle(surface, color, center, radius)

    def ghost_center(self, state: Connect4State) -> tuple[int, int] | None:
        """落子预览的中心 = **落点槽位的中心**，没有悬停时返回 ``None``。

        必须严丝合缝地落在槽位里：一旦为了"浮在空中"给个纵向偏移，
        预览就会压在槽位边缘上，看着像错位。
        """
        if self._hover_col is None:
            return None
        return self.cell_center(self._hover_col, state.heights[self._hover_col])

    def _draw_ghost(self, surface, state: Connect4State) -> None:
        """悬停预览：在落点槽位里画一个半透明的棋子（与圆窝同尺寸、同心）。"""
        center = self.ghost_center(state)
        if center is None:
            return
        # 索引是**玩家号 0/1**，不是棋子值 1/2（那是 cells 里的约定）
        player = state.current
        radius = self.socket_radius
        layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*theme.PLAYER_COLORS[player], 150), (radius, radius), radius)
        pygame.draw.circle(
            layer, (*theme.PLAYER_DARK[player], 200), (radius, radius), radius, 2
        )
        surface.blit(layer, (center[0] - radius, center[1] - radius))

    def _disc_is_last_move(self, col: int, row: int, player: int) -> bool:
        """这一枚是不是"刚下上去的那一手"（高亮用）。"""
        last = self._last_move
        return (
            isinstance(last, DropMove)
            and last.col == col
            and last.row == row
            and last.player == player
        )

    def _draw_discs(self, surface, state: Connect4State) -> None:
        """画所有棋子。

        正在下落的那一枚**最后画**：它要从棋盘上沿一路穿过已有棋子掉到落点，
        先画就会被沿途的棋子盖住，看着像钻进棋盘里消失了。
        """
        anim = self._anim
        falling: tuple[int, int, int] | None = None
        for row in range(state.rows):
            for col in range(state.cols):
                who = state.cells[row * state.cols + col]
                if not who:
                    continue
                player = who - 1
                # 只有"最后一手的那一枚"才带偏移（照抄 Quoridor 的判据结构：
                # state 已 apply，靠 Move 里的 row/player 认领）
                if (
                    anim is not None
                    and anim.move.row == row
                    and anim.move.col == col
                    and anim.move.player == player
                ):
                    falling = (col, row, player)
                    continue
                self._draw_disc(
                    surface, self.cell_center(col, row), player,
                    active=self._disc_is_last_move(col, row, player),
                )
        if anim is not None and falling is not None:
            col, row, player = falling
            self._draw_disc(
                surface, self.cell_center(col, row), player, anim.tween.offset(),
                active=self._disc_is_last_move(col, row, player),
                shadow_scale=anim.tween.progress,
            )

    def _draw_win_line(
        self, surface, state: Connect4State, *, active: bool = True
    ) -> None:
        if not self._win_line or not active or state.winner_player is None:
            return
        # 同上：winner_player 是玩家号 0/1，直接当调色板索引用
        color = theme.PLAYER_COLORS[state.winner_player]
        for col, row in self._win_line:
            center = self.cell_center(col, row)
            radius = self.socket_radius
            pygame.draw.circle(surface, color, center, radius + 3, 3)
            pygame.draw.circle(surface, theme.SELECT_RING, center, radius + 6, 1)

    def _draw_disc(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        player: int,
        dy: float = 0,
        *,
        active: bool = False,
        shadow_scale: float = 1.0,
    ) -> None:
        """画一枚棋子：落地阴影 → 暗边 → 主体 → 高光。"""
        radius = self.socket_radius
        cx = center[0]
        cy = int(center[1] + dy)
        color = theme.PLAYER_COLORS[player]
        dark = theme.PLAYER_DARK[player]

        if active:
            render.circle_glow(surface, (cx, cy), radius, color, layers=4, max_alpha=90)
        # 阴影随高度淡出、变远
        shadow_alpha = int(120 * max(0.0, min(1.0, shadow_scale)))
        if shadow_alpha > 8:
            offset = int(3 + (1.0 - shadow_scale) * 6)
            layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                layer, (*theme.SHADOW, shadow_alpha), (radius, radius), radius
            )
            surface.blit(layer, (cx - radius, cy - radius + offset))
        pygame.draw.circle(surface, dark, (cx, cy), radius)
        pygame.draw.circle(surface, color, (cx, cy), max(2, radius - max(1, radius // 12)))
        pygame.draw.circle(
            surface, theme.lighten(color, 0.40),
            (cx - radius // 3, cy - radius // 3), max(2, radius // 3),
        )
        if active:
            pygame.draw.circle(surface, theme.SELECT_RING, (cx, cy), radius + 3, 2)


def make_view() -> Connect4View:
    """视图工厂（注册表用）。"""
    return Connect4View()


__all__ = ["Connect4View", "make_view"]
