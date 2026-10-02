"""状态抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class State(ABC):
    """局面。

    **约定：状态不可变**。`Game.apply` 必须返回新对象而非原地修改，
    这样悔棋（快照栈）、AI 搜索（树展开）、多线程读取都可以零成本共享。
    """

    __slots__ = ()

    @property
    @abstractmethod
    def current_player(self) -> int:
        """当前该谁走。"""

    @abstractmethod
    def is_terminal(self) -> bool:
        """是否已终局。"""

    @abstractmethod
    def winner(self) -> int | None:
        """获胜方；未终局返回 None。"""

    @abstractmethod
    def zobrist_hash(self) -> int:
        """用于置换表 / MCTS 复用的局面哈希。"""
