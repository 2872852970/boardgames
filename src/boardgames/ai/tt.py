"""置换表（Transposition Table）。"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.move import Move

EXACT = 0
LOWER = 1  # 该分数是下界（发生了 beta 截断）
UPPER = 2  # 该分数是上界（没有超过 alpha）


@dataclass(slots=True)
class TTEntry:
    depth: int
    flag: int
    score: float
    move: Move | None


class TranspositionTable:
    """以局面哈希为键的定长表；满了就整体清空（简单且足够）。"""

    __slots__ = ("_table", "max_size", "hits", "stores")

    def __init__(self, max_size: int = 200_000):
        self._table: dict[int, TTEntry] = {}
        self.max_size = max_size
        self.hits = 0
        self.stores = 0

    def get(self, key: int) -> TTEntry | None:
        entry = self._table.get(key)
        if entry is not None:
            self.hits += 1
        return entry

    def put(self, key: int, entry: TTEntry) -> None:
        if len(self._table) >= self.max_size:
            self._table.clear()
        self._table[key] = entry
        self.stores += 1

    def clear(self) -> None:
        self._table.clear()

    def __len__(self) -> int:
        return len(self._table)
