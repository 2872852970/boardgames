"""四子棋的着法：向某一列投一枚棋子。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.move import Move


@dataclass(frozen=True, slots=True)
class DropMove(Move):
    """把一枚棋子投进第 ``col`` 列，它会落到第 ``row`` 行。

    ``row`` 和 ``player`` 都要存，不能只存 ``col``：

    * ``row`` 决定棋子画在哪一格 —— ``heights[col] - 1`` 只在"这一步刚落下"时正确，
      悔棋 / 新局之后就不对了；
    * ``player`` 决定颜色，且是视图识别"这一枚正在播放下落动画"的唯一判据。
    """

    col: int
    row: int
    player: int

    @property
    def is_placement(self) -> bool:
        # 刻意保持 False：框架用它判断"放完是否退出放置模式"，
        # 四子棋没有放墙模式，返回 True 只会引入无意义的模式翻转。
        return False

    def describe(self) -> str:
        return f"第 {self.col + 1} 列落子"
