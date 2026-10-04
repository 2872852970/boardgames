"""点格棋的着法：在相邻两点间画一条边。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.move import Move


@dataclass(frozen=True, slots=True)
class EdgeMove(Move):
    """画一条边。

    * ``orient``：``0`` = 水平边，``1`` = 垂直边。
    * ``row`` / ``col``：边的锚点坐标（水平边锚在左端点，垂直边锚在上端点）。
    * ``player``：画边的人（用于视图高亮，额外回合时连续同一人）。

    ``is_placement`` 保持 ``False`` —— 画边不是"放置模式"（放墙）那种交互，
    而是点格棋的**唯一**着法类型。
    """

    orient: int
    row: int
    col: int
    player: int

    def describe(self) -> str:
        direction = "横" if self.orient == 0 else "竖"
        return f"第{self.row + 1}行第{self.col + 1}点画{direction}边"
