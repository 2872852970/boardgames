"""着法抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Move(ABC):
    """一步着法。

    子类必须是**可哈希、可比较**的不可变对象：
    AI 的置换表、MCTS 的子节点字典都以 Move 作为键。
    """

    __slots__ = ()

    @property
    def is_placement(self) -> bool:
        """是否是"放置型"着法（例如放墙）。

        框架用它来决定放完之后要不要退出放置模式，从而不必知道具体棋类。
        """
        return False

    @abstractmethod
    def describe(self) -> str:
        """返回人类可读的描述，用于日志/调试。"""

    def __repr__(self) -> str:  # pragma: no cover - 便捷调试
        return f"{type(self).__name__}({self.describe()})"
