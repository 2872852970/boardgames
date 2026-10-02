"""Quoridor 着法。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.move import Move
from boardgames.games.quoridor.geometry import Pos

_DIR_NAMES = {
    (0, -1): "上",
    (0, 1): "下",
    (-1, 0): "左",
    (1, 0): "右",
}


@dataclass(frozen=True, slots=True)
class PawnMove(Move):
    """移动棋子。相邻一格为普通走子；隔一格为跳跃。"""

    src: Pos
    dst: Pos

    @property
    def is_jump(self) -> bool:
        return abs(self.dst[0] - self.src[0]) + abs(self.dst[1] - self.src[1]) == 2

    def describe(self) -> str:
        dx = self.dst[0] - self.src[0]
        dy = self.dst[1] - self.src[1]
        if self.is_jump:
            # 斜跳的方向用"沿跳跃轴"命名，便于日志阅读
            if dy == 0:
                return f"跳向{'右' if dx > 0 else '左'}"
            if dx == 0:
                return f"跳向{'下' if dy > 0 else '上'}"
            return f"跳跃到{(self.dst[0], self.dst[1])}"
        return f"移动到{_DIR_NAMES.get((dx, dy), (dx, dy))}"


@dataclass(frozen=True, slots=True)
class WallMove(Move):
    """放置一面墙。``orient`` 为 ``"h"``（水平）或 ``"v"``（垂直）。"""

    orient: str
    ax: int
    ay: int

    @property
    def is_placement(self) -> bool:
        return True

    def describe(self) -> str:
        kind = "横墙" if self.orient == "h" else "竖墙"
        return f"放{kind}@({self.ax},{self.ay})"

    @property
    def wall(self) -> tuple[str, int, int]:
        return (self.orient, self.ax, self.ay)
