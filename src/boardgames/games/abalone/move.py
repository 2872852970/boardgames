"""大力士棋的着法：把一串（1~3 枚）己方棋子朝某个方向推一格。"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardgames.core.move import Move
from boardgames.games.abalone.geometry import DIRECTION_NAMES, DIRECTIONS, INDEX, Pos, group_axis


@dataclass(frozen=True, slots=True)
class AbaloneMove(Move):
    """一次移动。

    ``player`` / ``cells`` / ``direction`` 是**身份字段**（参与 ``==`` 与 ``hash``）；
    ``pushed`` / ``ejected`` 只是给视图播动画用的**附带信息**，必须 ``compare=False``：

    * 视图构造出来的 Move 与 :meth:`AbaloneGame.legal_moves` 产出的 Move 必须能相等，
      否则 :meth:`~boardgames.games.abalone.rules.AbaloneGame.is_legal` 会判非法；
    * MCTS 用 ``dict[Move, _Node]`` 存子节点，若这两个字段参与比较，同一手会因为
      携带信息不同而被当成两个不同的子节点。

    为什么非存不可：``MatchScene._play_move()`` 是**先** ``view.animate(move, ms)``
    **再** ``session.play(move)`` —— 播动画时视图拿不到"前一局面"，只能靠 Move 自带。
    """

    player: int
    #: 被移动的己方棋子（按 ``(q, r)`` 字典序排定，保证同一手只有一种写法）
    cells: tuple[Pos, ...]
    #: 方向下标（0..5，见 :mod:`~boardgames.games.abalone.geometry`）
    direction: int
    #: 被推动但仍留在盘上的对手棋子（沿 ``direction`` 各前进一格）
    pushed: tuple[Pos, ...] = field(default=(), compare=False, repr=False)
    #: 被推出盘外的那一枚对手棋子（至多一枚）
    ejected: Pos | None = field(default=None, compare=False, repr=False)

    @property
    def is_placement(self) -> bool:
        # 大力士棋没有"放置型"着法，保持默认 False。
        return False

    def destinations(self) -> tuple[Pos, ...]:
        """会位移的棋子在**这一手之后**所处的格子（己方 + 被推的），盘外的不计。

        语义必须是**目标格而不是源格**：``MatchScene._play_move()`` 先把 Move 交给视图、
        再 ``session.play()``，于是 :meth:`AbaloneView.draw` 拿到的永远是**走完之后**
        的局面 —— 按源格去比对等于一个都对不上，表现出来就是"棋子瞬移，动画没播"。

        ``ejected`` 不在这里：它已经不在盘上了（也不在任何局面里），
        视图单独把它从源格朝盘外滑出去并淡出。
        """
        dq, dr = DIRECTIONS[self.direction]
        moved = tuple((q + dq, r + dr) for q, r in self.cells + self.pushed)
        return tuple(pos for pos in moved if pos in INDEX)

    def describe(self) -> str:
        name = DIRECTION_NAMES[self.direction]
        text = f"{len(self.cells)} 子向 {name} "
        if self.ejected is not None:
            return text + "推进 · 挤出 1 子"
        if self.pushed:
            return text + f"推进 · 推动 {len(self.pushed)} 子"
        if len(self.cells) > 1:  # 单子无所谓直线 / 横移
            indices = tuple(INDEX[p] for p in self.cells)
            kind = "直线" if self.direction % 3 == group_axis(indices) else "横移"
            return text + kind
        return text + "移动"
