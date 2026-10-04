"""点格棋（Dots and Boxes）的不可变局面。

拓扑约定
--------
棋盘是 ``size × size`` 个**点**（``size = 6`` 是正式比赛规格），这些点围成
``(size-1) × (size-1)`` 个**方格**。玩家轮流在相邻两点间画一条边；画满一个
方格的第四条边即占领该格，并**再走一手**。

数据结构（全部用一维元组，切片复制与哈希都最廉价）：

* ``h_edges``：**水平边**，长度 ``size * (size-1)``，下标 ``row * (size-1) + col``
  表示"第 ``row`` 行点、第 ``col`` 列点 到 第 ``col+1`` 列点"之间那条边。
  取值 0 空 / 1 玩家1 / 2 玩家2（**谁画的**，用于双方颜色区分）。
* ``v_edges``：**垂直边**，长度 ``(size-1) * size``，下标 ``row * size + col``
  表示"第 ``row`` 行点 到 第 ``row+1`` 行点、第 ``col`` 列点"之间那条边。
  取值同上。
* ``boxes``：**方格归属**，长度 ``(size-1) * (size-1)``，0 空 / 1 玩家1 / 2 玩家2。
  下标 ``row * (size-1) + col`` 的方格，其四条边分别是：
  顶 ``h[row][col]``、底 ``h[row+1][col]``、左 ``v[row][col]``、右 ``v[row][col+1]``。

``scores`` 是**冗余**字段（= 双方占领格数），与 ``boxes`` 恒一致，用于评估与侧栏
显示的 O(1) 读取。``current`` 是当前该画边的玩家索引（0/1）—— 注意：围成格子时
**不翻转** ``current``（额外回合），画边没围成时才翻。
"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.state import State

DEFAULT_SIZE = 6

EMPTY = 0


@dataclass(frozen=True, slots=True)
class DotsBoxesState(State):
    """一局点格棋的局面。**不可变**，悔棋 / 搜索 / 多线程都靠这一点。"""

    size: int
    #: 水平边，长度 size*(size-1)，0 空 / 1 玩家1 / 2 玩家2（谁画的）
    h_edges: tuple[int, ...]
    #: 垂直边，长度 (size-1)*size，0 空 / 1 玩家1 / 2 玩家2
    v_edges: tuple[int, ...]
    #: 方格归属，长度 (size-1)*(size-1)，0 空 / 1 玩家1 / 2 玩家2
    boxes: tuple[int, ...]
    #: 双方占领格数（冗余，与 boxes 恒一致）
    scores: tuple[int, int]
    current: int
    ply: int
    #: 获胜的玩家索引（0/1），未终局为 None；平局也是 None
    winner_player: int | None = None

    # ---- 下标换算 ----

    @property
    def grid(self) -> int:
        """方格边长（每边多少格）。"""
        return self.size - 1

    def h_index(self, row: int, col: int) -> int:
        return row * (self.size - 1) + col

    def v_index(self, row: int, col: int) -> int:
        return row * self.size + col

    def box_index(self, row: int, col: int) -> int:
        return row * (self.size - 1) + col

    # ---- State 抽象 ----

    @property
    def current_player(self) -> int:
        return self.current

    def winner(self) -> int | None:
        return self.winner_player

    def is_terminal(self) -> bool:
        """所有边都画完即终局。O(1)：靠 ply 计数（每画一条边 ply+1）。"""
        if self.winner_player is not None:
            return True
        total_edges = self.size * (self.size - 1) * 2
        return self.ply >= total_edges

    def is_full(self) -> bool:
        return self.is_terminal()

    def zobrist_hash(self) -> int:
        # current / scores / winner 都能从 h_edges + v_edges 推出，
        # 排除掉可提高置换表命中率。
        return hash((self.size, self.h_edges, self.v_edges, self.current))

    # ---- 便捷方法 ----

    def box_owner(self, row: int, col: int) -> int:
        """方格 ``(row, col)`` 的归属（0 空 / 1 / 2）。"""
        return self.boxes[self.box_index(row, col)]

    def is_box_closed(self, row: int, col: int) -> bool:
        """方格四条边是否都已画上。"""
        top = self.h_edges[self.h_index(row, col)]
        bottom = self.h_edges[self.h_index(row + 1, col)]
        left = self.v_edges[self.v_index(row, col)]
        right = self.v_edges[self.v_index(row, col + 1)]
        return bool(top and bottom and left and right)

    def edge_count(self) -> tuple[int, int]:
        """(已画边数, 总边数)。"""
        total = self.size * (self.size - 1) * 2
        drawn = sum(1 for v in self.h_edges if v) + sum(1 for v in self.v_edges if v)
        return drawn, total


def initial_state(size: int = DEFAULT_SIZE, first_player: int = 0) -> DotsBoxesState:
    n = int(size)
    return DotsBoxesState(
        size=n,
        h_edges=(0,) * (n * (n - 1)),
        v_edges=(0,) * ((n - 1) * n),
        boxes=(0,) * ((n - 1) * (n - 1)),
        scores=(0, 0),
        current=first_player,
        ply=0,
        winner_player=None,
    )
