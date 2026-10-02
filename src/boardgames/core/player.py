"""玩家标识与元信息。"""

from __future__ import annotations

from dataclasses import dataclass

#: 玩家标识，从 0 开始。多数棋类为 2 人，但接口不限制人数。
PlayerId = int


@dataclass(frozen=True)
class PlayerMeta:
    """玩家展示信息（供 UI 使用）。"""

    name: str
    color: tuple[int, int, int]
