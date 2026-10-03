"""重力四子棋的不可变局面。

坐标约定
--------
``(col, row)``，``col`` 向右、``row`` 向下（0 是最底行）。
棋盘只存成一维元组 ``cells``，下标 ``row * cols + col``，取值 0 空 / 1 玩家1 / 2 玩家2。

为什么不存二维元组：一维元组复制是单次切片（``cells[:i] + (v,) + cells[i+1:]``），
``hash`` / ``==`` 也更廉价，视图层取格子是 ``cells[r*cols+c]`` 而不用两层解包。
42~120 格的规模用元组绰绰有余，位掩码反而不好读。

``heights`` 是**冗余**字段，但它必须是：投子目标行 = ``heights[col]``，
而评估函数的威胁检测要遍历所有列的"下一格"。若每次从 ``cells`` 推导就是
O(cols×rows)，而这段代码在 MCTS 的 rollout 里会被调用上百万次。
它只由 :meth:`Connect4Game.apply` 写入，因此永远与 ``cells`` 一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.state import State

DEFAULT_COLS = 7
DEFAULT_ROWS = 6
#: 标准四子棋（用户已确认：连线数固定，不开放配置）
CONNECT_TO = 4

EMPTY = 0

#: 四个连线方向：横、竖、两种斜
DIRECTIONS: tuple[tuple[int, int], ...] = ((0, 1), (1, 0), (1, 1), (1, -1))


def scan_win(cells: tuple[int, ...], cols: int, rows: int, row: int, col: int, who: int) -> bool:
    """从 ``(row, col)`` 向**两侧**延伸，判断 ``who`` 是否连成 ``CONNECT_TO`` 子。

    落点两侧的连子数必须**相加**再比较，不能各自独立判断：否则"落点正好补上
    横四/斜四中间那一子"（``X.XX`` 投中间变 ``XXXX``）永远判不出来。
    """
    for dr, dc in DIRECTIONS:
        total = 1  # 落点自己
        for sign in (1, -1):
            count = 0
            for step in range(1, CONNECT_TO):
                rr = row + dr * step * sign
                cc = col + dc * step * sign
                if not (0 <= rr < rows and 0 <= cc < cols):
                    break
                if cells[rr * cols + cc] != who:
                    break
                count += 1
            total += count
            if total >= CONNECT_TO:
                return True
    return False


@dataclass(frozen=True)
class Connect4State(State):
    """一局四子棋的局面。**不可变**，悔棋 / 搜索 / 多线程都靠这一点。"""

    cols: int
    rows: int
    #: 一维棋盘，``row * cols + col``，0 空 / 1 玩家1 / 2 玩家2
    cells: tuple[int, ...]
    #: 每列已填高度（冗余，见模块文档）
    heights: tuple[int, ...]
    current: int
    ply: int
    #: 胜利的**玩家索引**（0 或 1，None 表示还没人赢），apply 时算出并缓存。
    #:
    #: 刻意**不叫** ``winner`` —— ``State.winner()`` 是 ABC 的抽象方法，
    #: 同名字段会把它遮蔽掉，引擎侧 ``state.winner()`` 就会拿到非可调用对象。
    #:
    #: 用**玩家索引**（0/1）而不是 ``cells`` 里的棋子值（1/2），是为了和
    #: ``State.current_player`` / ``GameSession.winner()`` 同一套语义 ——
    #: 引擎（minimax / mcts）会拿 ``state.winner()`` 直接和玩家索引比较。
    winner_player: int | None = None

    @property
    def current_player(self) -> int:
        return self.current

    @property
    def opponent(self) -> int:
        return 1 - self.current

    def winner(self) -> int | None:
        return self.winner_player

    def is_terminal(self) -> bool:
        """分出胜负，或棋盘已填满（后者是平局）。"""
        if self.winner_player is not None:
            return True
        return all(h >= self.rows for h in self.heights)

    def is_full(self) -> bool:
        return all(h >= self.rows for h in self.heights)

    def zobrist_hash(self) -> int:
        # heights / ply / winner_player 都能从 cells 推出，排除掉可以提高置换表命中率
        return hash((self.cols, self.rows, self.cells, self.current))

    def at(self, col: int, row: int) -> int:
        return self.cells[row * self.cols + col]

    def drop_row(self, col: int) -> int | None:
        """投子到第 ``col`` 列会落在第几行；该列已满则返回 ``None``。"""
        h = self.heights[col]
        return h if h < self.rows else None

    def count_pieces(self) -> tuple[int, int]:
        """双方的已落子数。"""
        p0 = sum(1 for v in self.cells if v == 1)
        return p0, len(self.cells) - self.heights_total() - p0

    def heights_total(self) -> int:
        return sum(self.heights)

    def winning_line(self) -> tuple[tuple[int, int], ...] | None:
        """找出胜利的四个格子（用于高亮），没有则返回 ``None``。

        局面已缓存了 ``winner_player``，但**连线的位置**没缓存，所以现算一次。
        只在终局绘制时调用，不在搜索热路径上。
        """
        if self.winner_player is None:
            return None
        who = self.winner_player + 1
        for row in range(self.rows):
            for col in range(self.cols):
                if self.cells[row * self.cols + col] != who:
                    continue
                for dr, dc in DIRECTIONS:
                    # 只从这条线的**起点**出发（往回一格不是自己）
                    pr, pc = row - dr, col - dc
                    if (
                        0 <= pr < self.rows
                        and 0 <= pc < self.cols
                        and self.cells[pr * self.cols + pc] == who
                    ):
                        continue
                    line = []
                    rr, cc = row, col
                    for _ in range(CONNECT_TO):
                        if not (0 <= rr < self.rows and 0 <= cc < self.cols):
                            break
                        if self.cells[rr * self.cols + cc] != who:
                            break
                        line.append((cc, rr))
                        rr += dr
                        cc += dc
                    if len(line) == CONNECT_TO:
                        return tuple(line)
        return None


def initial_state(cols: int = DEFAULT_COLS, rows: int = DEFAULT_ROWS, first_player: int = 0) -> Connect4State:
    return Connect4State(
        cols=cols,
        rows=rows,
        cells=(EMPTY,) * (cols * rows),
        heights=(0,) * cols,
        current=first_player,
        ply=0,
        winner_player=None,
    )
