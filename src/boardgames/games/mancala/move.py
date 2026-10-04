"""播棋的着法：从己方某个小坑取出全部种子进行播种。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.move import Move


@dataclass(frozen=True, slots=True)
class SowMove(Move):
    """从第 ``pit`` 个小坑（下标，见 state.py）取出全部种子播种。

    ``player`` 是执行播种的人。额外回合时同一位玩家会连续产生多个 SowMove。
    """

    pit: int
    player: int

    def describe(self) -> str:
        return f"播种第 {self.pit + 1} 号坑"
