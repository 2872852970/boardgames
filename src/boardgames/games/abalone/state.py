"""大力士棋的不可变局面。

存储约定
--------
``cells`` 是 61 长的一维元组（下标 = :data:`~boardgames.games.abalone.geometry.INDEX`），
取值 0 空 / 1 玩家1 / 2 玩家2。和四子棋一样**不用位掩码**：单格替换是
``cells[:i] + (v,) + cells[i+1:]``，约 0.2 µs；而整局 ``legal_moves`` 的全量生成
约 44 µs —— 位掩码省下的那点时间远不抵可读性损失，以及"测试里直接手搭局面"的
脆弱性（位掩码没法一眼看出摆成了什么样）。

``out[p]`` 是 **``p`` 把对手推出去的子数**（不是"``p`` 自己被推出去的"）。
这样 :meth:`is_terminal` 与 :meth:`winner` 的判据直接合拍（``out[p] >= 6`` ⇒
``p`` 获胜），评估函数里也不用做索引翻转。
"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.state import State
from boardgames.games.abalone.geometry import CELL_COUNT, INDEX, Pos
from boardgames.games.abalone.layouts import DEFAULT_SETUP, WIN_OUT, setup_cells

_WIN_OUT = WIN_OUT  # 少写一层属性查找：is_terminal 在 rollout 里每步都会走到
EMPTY = 0


@dataclass(frozen=True)
class AbaloneState(State):
    """一局大力士棋的局面。**不可变** —— 悔棋 / AI 搜索 / 后台线程都靠这一点。"""

    #: 61 格棋盘，0 空 / 1 玩家1 / 2 玩家2
    cells: tuple[int, ...]
    #: ``out[p]`` = ``p`` 已把对手推出盘外的子数
    out: tuple[int, int]
    current: int
    ply: int
    #: 获胜的**玩家索引**（0/1），None 表示还没分出胜负。
    #:
    #: 刻意**不叫** ``winner`` —— ``State.winner()`` 是 ABC 的抽象方法，
    #: 同名字段会把它遮蔽掉，引擎侧 ``state.winner()`` 就会拿到非可调用对象。
    winner_player: int | None = None

    @property
    def current_player(self) -> int:
        return self.current

    @property
    def opponent(self) -> int:
        return 1 - self.current

    def is_terminal(self) -> bool:
        """终局判据：挤出 6 枚，**或**行棋方在盘上一枚子都不剩。

        第二条是防御性的：正常对局（28 枚守恒）里对手推满 6 枚早就触发第一条了，
        但手搭的稀疏局面（测试、以及将来的"残局"摆法）可能出现"某方已无子可动"。
        少了这条，:meth:`~boardgames.games.abalone.rules.AbaloneGame.legal_moves`
        会返回空表，而 MCTS 的 rollout 循环只拿 ``is_terminal()`` 当出口 ——
        于是它会在非终局且无处可走的节点上反复索取着法直到抛
        ``RuntimeError``（AI 线程吞掉异常，表现是"AI 突然不下棋了"）。

        这里用 :meth:`marble_count`（一次 61 长的遍历）而不是 ``legal_moves``：
        ``is_terminal`` 在 rollout 循环里每步都调用，多一层全量着法生成会让
        MCTS 直接慢一倍。
        """
        if self.out[0] >= _WIN_OUT or self.out[1] >= _WIN_OUT:
            return True
        return self.marble_count()[self.current] == 0

    def winner(self) -> int | None:
        return self.winner_player

    def zobrist_hash(self) -> int:
        # out / ply / winner_player 都能从 cells 推出（某方在盘上的子数 =
        # 14 - 对手的 out），排除掉可以提高置换表命中率。
        return hash((self.cells, self.current))

    def at(self, pos: Pos) -> int:
        """该格内容（0 空 / 1 玩家1 / 2 玩家2）。"""
        return self.cells[INDEX[pos]]

    def at_index(self, index: int) -> int:
        return self.cells[index]

    def marble_count(self) -> tuple[int, int]:
        """双方**仍在盘上**的子数（供侧栏显示）。"""
        p0 = sum(1 for v in self.cells if v == 1)
        return p0, sum(1 for v in self.cells if v == 2)


def initial_state(setup: str = DEFAULT_SETUP, first_player: int = 0) -> AbaloneState:
    """按 ``setup`` 摆出开局；``first_player`` 是玩家索引（0 = 黑 / 先手）。"""
    p0, p1 = setup_cells(setup)
    cells = [EMPTY] * CELL_COUNT
    for pos in p0:
        cells[INDEX[pos]] = 1
    for pos in p1:
        cells[INDEX[pos]] = 2
    return AbaloneState(
        cells=tuple(cells),
        out=(0, 0),
        current=first_player,
        ply=0,
        winner_player=None,
    )
