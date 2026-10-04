"""播棋的棋盘渲染与交互。

**只用鼠标**：点己方一侧某个小坑即播种。悬停会高亮该坑，并沿逆时针方向预览整条
播种路径（每个落点一个浅色标记，最后一粒落点用亮色圈出）。

布局：上下两排小坑（玩家 0 在下排、玩家 1 在上排），两端各一个大仓库
（玩家 0 在右下、玩家 1 在左上）。整块棋盘在可用区里**居中**。

种子可视化：「示意分法 + 具体数字」—— 每个坑 / 仓库里既画出一堆按黄金角排布的
种子小点（示意这一共有多少），又写出确切的数字，二者结合一眼就能数清。

动画：落子时种子沿播种路径逐坑「飞入」—— 先把手里的种子从起点坑清空，再沿路径
一格一格地长出来，并有一颗正在飞的小种子在起点与当前落点之间移动。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from boardgames.core.move import Move
from boardgames.games.mancala.move import SowMove
from boardgames.games.mancala.state import MancalaState, sow_path
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

#: 种子的颜色（暖色，和棋盘底区分开）
SEED_FILL: tuple[int, int, int] = (224, 198, 150)
SEED_DARK: tuple[int, int, int] = (176, 146, 100)


@dataclass
class _SowAnim:
    """一次播种动画的快照：落子前 / 后局面 + 落点路径 + 补间。"""

    move: SowMove
    pre: MancalaState
    post: MancalaState
    path: list[tuple[int, bool]]
    tween: Tween


class MancalaView:
    """播棋的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 400)
        self.cell = 60
        self.origin = (0, 0)
        self.pits_per_side = 6
        self._hover: SowMove | None = None
        self._last_move: Move | None = None
        self._hover_path: list[tuple[int, bool]] | None = None
        # 动画用的快照（draw 时记下上一帧局面，animate 时据此算落子后局面）
        self._state: MancalaState | None = None
        self._game = None
        self._anim: _SowAnim | None = None

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        p = self.pits_per_side
        # 棋盘宽 (p+2) 格、高 2 格；cell 取宽 / 高里较紧的约束，并在可用区里居中
        cell = int(min(area.width / (p + 3), area.height / 3))
        self.cell = max(28, cell)
        board_w = self.cell * (p + 2)
        board_h = self.cell * 2
        self.origin = (
            area.x + (area.width - board_w) // 2,
            area.y + (area.height - board_h) // 2,
        )

    def set_pits(self, pits_per_side: int) -> None:
        self.pits_per_side = pits_per_side
        self.layout(self.area)

    # ---- 几何 ----

    def _pit_slot_x(self, col: int) -> int:
        return self.origin[0] + (col + 1) * self.cell + self.cell // 2

    def _store_x(self, side: int) -> int:
        # 玩家 0 的仓库在**右端**（紧挨他下排最右的坑），玩家 1 的在左端；
        # 这样播种沿「下排向右 → 右端仓库 → 上排向左 → 左端仓库」连续绕圈，
        # 种子不会在屏幕上瞬移。
        if side == 0:
            return self.origin[0] + (self.pits_per_side + 1) * self.cell + self.cell // 2
        return self.origin[0] + self.cell // 2

    def _pit_center(self, player: int, col: int) -> tuple[int, int]:
        x = self._pit_slot_x(col)
        # 玩家 0 在下排，玩家 1 在上排
        y = self.origin[1] + (self._board_h() // 2) + self.cell // 2
        if player == 1:
            y = self.origin[1] + (self._board_h() // 2) - self.cell // 2
        return x, y

    def _store_center(self, player: int) -> tuple[int, int]:
        x = self._store_x(player)
        y = self.origin[1] + self._board_h() // 2
        return x, y

    def _board_h(self) -> int:
        return self.cell * 2

    def board_rect(self) -> pygame.Rect:
        w = self.cell * (self.pits_per_side + 2)
        h = self._board_h()
        return pygame.Rect(self.origin[0], self.origin[1], w, h)

    # ------------------------------------------------------------------ #
    # 命中测试
    # ------------------------------------------------------------------ #

    def _pit_at(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """像素 → (玩家索引, 列号)。"""
        px, py = pos
        r = self.cell // 2
        for player in (0, 1):
            for col in range(self.pits_per_side):
                cx, cy = self._pit_center(player, col)
                if abs(px - cx) <= r and abs(py - cy) <= r:
                    return player, col
        return None

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #

    def _col_to_pit(self, player: int, col: int) -> int:
        # 两排都从左到右按下标递增显示：下排 0..p-1、上排 p..2p-1，
        # 同一列上下两坑下标正好差 p（= state.opposite 的"正对面"）。
        p = self.pits_per_side
        if player == 0:
            return col
        return p + col

    def _pit_to_col(self, player: int, pit: int) -> int:
        p = self.pits_per_side
        if player == 0:
            return pit
        return pit - p

    def handle_motion(self, pos, game, state, view: ViewState) -> None:
        view.mouse = pos
        if not isinstance(state, MancalaState) or state.is_terminal():
            self._hover = None
            self._hover_path = None
            return
        hit = self._pit_at(pos)
        if hit is None:
            self._hover = None
            self._hover_path = None
            return
        player, col = hit
        if player != state.current:
            self._hover = None
            self._hover_path = None
            return
        pit = self._col_to_pit(player, col)
        move = SowMove(pit, state.current)
        if not game.is_legal(state, move):
            self._hover = None
            self._hover_path = None
            return
        self._hover = move
        self._hover_path = sow_path(
            state.pits_per_side, pit, state.current, state.pits[pit]
        )

    def handle_click(self, pos, game, state, view: ViewState) -> Move | None:
        if not isinstance(state, MancalaState) or state.is_terminal():
            return None
        hit = self._pit_at(pos)
        if hit is None:
            return None
        player, col = hit
        if player != state.current:
            return None
        pit = self._col_to_pit(player, col)
        move = SowMove(pit, state.current)
        if not game.is_legal(state, move):
            return None
        return move

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        if self._hover is None:
            return "点己方一侧的小坑播种", theme.TEXT_FAINT
        return f"播种第 {self._hover.pit + 1} 号坑", theme.ACCENT

    def hud_hint(self, *, wall_mode: bool = False, paused: bool = False) -> str:
        if paused:
            return "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        return "点己方小坑取种子逐坑播种 · 落己方仓库可再走 · 仓库多者胜"

    def in_placement_mode(self) -> bool:
        return False

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #

    def animate(self, move: Move, duration_ms: int) -> None:
        if duration_ms <= 0 or not isinstance(move, SowMove) or self._state is None:
            return
        pre = self._state
        # 用上一帧记下的 game 或现造一个来算落子后局面（含额外回合 / 捕获）
        game = self._game
        if game is None:
            from boardgames.games.mancala.rules import MancalaGame

            game = MancalaGame(pits_per_side=pre.pits_per_side)
        post = game.apply(pre, move)
        path = sow_path(pre.pits_per_side, move.pit, move.player, pre.pits[move.pit])
        self._anim = _SowAnim(
            move, pre, post, path, Tween(duration_s=duration_ms / 1000.0)
        )

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
        self._hover = None
        self._last_move = None
        self._hover_path = None
        self._anim = None

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
        state: MancalaState,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        self._state = state
        self._game = game
        if state.pits_per_side != self.pits_per_side:
            self.set_pits(state.pits_per_side)

        current_side = state.current
        if self._anim is not None:
            # 动画期间用快照渲染，不受状态是否 apply 影响
            self._draw_animated(surface, fonts, current_side)
        else:
            self._render_board(surface, fonts, state.pits, state.stores, current_side)
            if interactive and self._hover is not None:
                self._draw_hover(surface, state)

    def _render_board(
        self,
        surface,
        fonts,
        pits,
        stores,
        current_side,
        *,
        highlight_pit: int | None = None,
        path_slots: set[tuple[int, bool]] | None = None,
    ) -> None:
        p = self.pits_per_side
        board = self.board_rect()
        render.panel(
            surface, board.inflate(16, 16), color=theme.BOARD_BG, radius=theme.RADIUS + 6
        )

        # 两侧底色：当前走子的一方更亮一点，提示「这一排是你的」
        for player in (0, 1):
            tint = theme.PLAYER_COLORS[player]
            y_top = self._pit_center(player, 0)[1] - self.cell // 2
            layer = pygame.Surface((self.cell * p, self.cell), pygame.SRCALPHA)
            layer.fill((*tint, 30 if player == current_side else 12))
            surface.blit(layer, (self.origin[0] + self.cell, y_top))

        # 仓库
        for player in (0, 1):
            self._draw_store(surface, fonts, player, stores[player])
        # 小坑
        for player in (0, 1):
            for col in range(p):
                pit = self._col_to_pit(player, col)
                on_path = path_slots is not None and (pit, False) in path_slots
                self._draw_pit(
                    surface, fonts, player, col, pit, pits[pit],
                    highlight=(pit == highlight_pit), on_path=on_path,
                )

        # 当前走子一方的那一排：描一圈玩家色，进一步提示归属
        if current_side is not None:
            row_y = self._pit_center(current_side, 0)[1]
            rr = pygame.Rect(
                self.origin[0] + self.cell, row_y - self.cell // 2,
                self.cell * p, self.cell,
            )
            render.rounded_rect(
                surface, rr, theme.PLAYER_COLORS[current_side], theme.RADIUS_SM, 2
            )

    def _draw_pit(
        self, surface, fonts, player, col, pit, seed_count, *,
        highlight: bool = False, on_path: bool = False,
    ) -> None:
        cx, cy = self._pit_center(player, col)
        r = self.cell // 2 - 6
        # 坑底
        pygame.draw.circle(surface, theme.CELL, (cx, cy), r)
        pygame.draw.circle(surface, theme.BORDER, (cx, cy), r, 2)
        if on_path:
            pygame.draw.circle(surface, theme.ACCENT, (cx, cy), r + 2, 2)
        if highlight:
            pygame.draw.circle(surface, theme.OK, (cx, cy), r + 4, 3)
        self._draw_seeds(surface, cx, cy, r, seed_count)
        self._draw_count(surface, fonts, cx, cy, r, seed_count)

    def _draw_store(self, surface, fonts, player, seed_count) -> None:
        cx, cy = self._store_center(player)
        r = self.cell // 2 - 6
        color = theme.PLAYER_COLORS[player]
        layer = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*color, 44), (r, r), r)
        surface.blit(layer, (cx - r, cy - r))
        pygame.draw.circle(surface, color, (cx, cy), r, 2)
        self._draw_seeds(surface, cx, cy, r, seed_count)
        self._draw_count(surface, fonts, cx, cy, r, seed_count)

    def _draw_seeds(self, surface, cx, cy, r, seed_count) -> None:
        """示意分法：在坑内按黄金角排布的小点堆。"""
        if seed_count <= 0:
            return
        seed_r = max(2, int(r * 0.17))
        for dx, dy in self._seed_offsets(seed_count, r):
            sx = cx + int(dx)
            sy = cy + int(dy) - int(r * 0.12)
            pygame.draw.circle(surface, SEED_DARK, (sx, sy), seed_r)
            pygame.draw.circle(surface, SEED_FILL, (sx, sy), max(1, seed_r - 1))

    def _draw_count(self, surface, fonts, cx, cy, r, seed_count) -> None:
        """具体数字：写在坑下方，带深色描边以便在种子堆上也能看清。"""
        font = fonts.get(max(11, self.cell // 5), bold=True)
        txt = str(seed_count)
        by = cy + r * 0.55
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            render.text(
                surface, font, txt, (cx + ox, int(by) + oy), theme.BG,
                align="center", baseline="middle",
            )
        render.text(
            surface, font, txt, (cx, int(by)), theme.TEXT,
            align="center", baseline="middle",
        )

    def _seed_offsets(self, n: int, r: int) -> list[tuple[float, float]]:
        """在半径 ``r`` 的圆内摆 ``n`` 颗种子（黄金角排布的紧凑堆），封顶 21 颗。"""
        if n <= 0:
            return []
        cap = 21
        n = min(n, cap)
        if n == 1:
            return [(0.0, 0.0)]
        out: list[tuple[float, float]] = [(0.0, 0.0)]
        golden = math.pi * (3.0 - math.sqrt(5.0))
        max_r = r * 0.78
        for i in range(1, n):
            radius = max_r * math.sqrt(i / (n - 1))
            ang = i * golden
            out.append((math.cos(ang) * radius, math.sin(ang) * radius))
        return out

    def _draw_animated(self, surface, fonts, current_side) -> None:
        anim = self._anim
        pre, post, path = anim.pre, anim.post, anim.path
        t = anim.tween.eased()
        pits = list(pre.pits)
        stores = list(pre.stores)
        # 起点坑：一开始就把种子掏空
        pits[anim.move.pit] = 0
        # 已经「飞到」的落点：一格一格长出来
        delivered = int(t * len(path) + 1e-6)
        for k in range(min(delivered, len(path))):
            idx, is_store = path[k]
            if is_store:
                stores[idx] += 1
            else:
                pits[idx] += 1
        if t >= 1.0 and post is not None:
            pits = list(post.pits)
            stores = list(post.stores)
        self._render_board(surface, fonts, pits, stores, current_side)

        # 正在「飞」的那一颗：在上一格与当前格之间移动的小点
        if delivered < len(path):
            idx, is_store = path[delivered]
            if is_store:
                tx, ty = self._store_center(idx)
            else:
                own = 0 if idx < self.pits_per_side else 1
                tx, ty = self._pit_center(own, self._pit_to_col(own, idx))
            sx, sy = self._pit_center(
                pre.current, self._pit_to_col(pre.current, anim.move.pit)
            )
            frac = max(0.0, min(1.0, (t * len(path)) - delivered))
            cx = sx + (tx - sx) * frac
            cy = sy + (ty - sy) * frac
            seed_r = max(3, int((self.cell // 2 - 6) * 0.22))
            pygame.draw.circle(surface, SEED_DARK, (int(cx), int(cy)), seed_r)
            pygame.draw.circle(surface, SEED_FILL, (int(cx), int(cy)), max(1, seed_r - 1))

    def _draw_hover(self, surface, state: MancalaState) -> None:
        """高亮选中的坑 + 整条播种路径预览（每个落点一个浅色标记）。"""
        move = self._hover
        if move is None:
            return
        player = move.player
        col = self._pit_to_col(player, move.pit)
        cx, cy = self._pit_center(player, col)
        r = self.cell // 2 - 6
        # 起点坑：亮色环
        pygame.draw.circle(surface, theme.OK, (cx, cy), r + 4, 3)
        # 整条播种路径：每个落点一个浅色标记，最后一粒落点用亮色圈出
        if self._hover_path:
            for k, (idx, is_store) in enumerate(self._hover_path):
                last = k == len(self._hover_path) - 1
                color = theme.OK if last else theme.ACCENT
                width = 3 if last else 2
                if is_store:
                    sc = self._store_center(idx)
                    pygame.draw.circle(surface, color, sc, r + 3, width)
                else:
                    own = 0 if idx < state.pits_per_side else 1
                    c2 = self._pit_to_col(own, idx)
                    pc = self._pit_center(own, c2)
                    pygame.draw.circle(surface, color, pc, r + 3, width)


def make_view() -> MancalaView:
    return MancalaView()


__all__ = ["MancalaView", "make_view"]
