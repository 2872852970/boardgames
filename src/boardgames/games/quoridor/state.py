"""Quoridor 局面（不可变）。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.state import State
from boardgames.games.quoridor.geometry import Pos

DEFAULT_SIZE = 9
DEFAULT_WALLS = 10
#: 水平墙压在水平网格线 ``y = ay+1`` 上，横跨 ``x ∈ [ax, ax+2]``。


@dataclass(frozen=True)
class QuoridorState(State):
    """一局 Quoridor 的完整局面。

    墙体用两个位掩码保存（``w = size-1`` 的方阵，位序 ``ay * w + ax``），
    因此复制/比较/哈希都极廉价；被阻断的边一律**按需派生**，不冗余存储。
    """

    size: int
    pawns: tuple[Pos, Pos]
    walls_left: tuple[int, int]
    h_mask: int
    v_mask: int
    current: int
    ply: int

    # ---- 坐标与目标 ----

    def goal_row(self, player: int) -> int:
        """`player` 的目标行：玩家 0 从下往上走，玩家 1 从上往下走。"""
        return 0 if player == 0 else self.size - 1

    def start_row(self, player: int) -> int:
        return self.size - 1 if player == 0 else 0

    @property
    def opponent(self) -> int:
        return 1 - self.current

    # ---- State 接口 ----

    @property
    def current_player(self) -> int:
        return self.current

    def is_terminal(self) -> bool:
        return self.winner() is not None

    def winner(self) -> int | None:
        for p in (0, 1):
            if self.pawns[p][1] == self.goal_row(p):
                return p
        return None

    def zobrist_hash(self) -> int:
        # 只含局面必需字段（不含 ply），提高置换表命中率。
        return hash(
            (
                self.size,
                self.pawns[0],
                self.pawns[1],
                self.walls_left,
                self.h_mask,
                self.v_mask,
                self.current,
            )
        )

    # ---- 便捷访问 ----

    def walls_of(self, player: int) -> int:
        return self.walls_left[player]

    def with_current(self, player: int) -> QuoridorState:
        """切换行动方（悔棋/调试用）。"""
        return QuoridorState(
            size=self.size,
            pawns=self.pawns,
            walls_left=self.walls_left,
            h_mask=self.h_mask,
            v_mask=self.v_mask,
            current=player,
            ply=self.ply,
        )

    def progress(self, player: int) -> int:
        """棋子距目标的曼哈顿进度（越大越接近）。"""
        return abs(self.pawns[player][1] - self.goal_row(player))


def initial_state(
    size: int = DEFAULT_SIZE,
    walls: int = DEFAULT_WALLS,
    first_player: int = 0,
) -> QuoridorState:
    """构造初始局面：双方棋子位于各自底边中央，各持 `walls` 面墙。"""
    mid = size // 2
    return QuoridorState(
        size=size,
        pawns=((mid, size - 1), (mid, 0)),
        walls_left=(walls, walls),
        h_mask=0,
        v_mask=0,
        current=first_player,
        ply=0,
    )
