"""终局原因。"""

from __future__ import annotations

from enum import Enum


class Termination(Enum):
    """对局结束的方式。"""

    ONGOING = "ongoing"
    WIN = "win"          # 正常达成胜利条件
    RESIGN = "resign"    # 认输
    DRAW = "draw"        # 平局（部分棋类才有）
