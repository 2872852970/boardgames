"""昆虫棋的着法：放置一枚新棋、移动一枚已入场的棋、停一手。

字段纪律（与大力士棋同一套约定）
--------------------------------
* ``player`` / ``src`` / ``dest`` / ``kind`` 等是**身份字段**，参与 ``==`` 与 ``hash``。
* 给视图播动画用的**附带信息必须** ``compare=False`` —— 否则视图构造出来的 Move
  与 :meth:`HiveGame.legal_moves` 产出的 Move 不相等，``is_legal`` 会判非法，
  而 MCTS 用 ``dict[Move, _Node]`` 存子节点，也会把同一手当成两个不同子节点。
* :meth:`destinations` 的语义必须是**目标格而不是源格**：
  ``MatchScene._play_move()`` 先 ``view.animate(move)``、再 ``session.play(move)``，
  视图拿到的是**走完之后**的局面，按源格比对等于一个都对不上。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardgames.core.move import Move
from boardgames.games.hive.geometry import Pos
from boardgames.games.hive.pieces import KIND_LABELS


def _fmt(pos: Pos) -> str:
    return f"({pos[0]},{pos[1]})"


@dataclass(frozen=True, slots=True)
class PlaceMove(Move):
    """从手牌里放一枚新棋到空格。"""

    player: int
    kind: str
    dest: Pos

    @property
    def is_placement(self) -> bool:
        # 真正的"放置型"着法。框架据此在落子后退出放墙模式（对昆虫棋无副作用，
        # 因为昆虫棋的视图把 in_placement_mode() 固定返回 False）。
        return True

    def destinations(self) -> tuple[Pos, ...]:
        return (self.dest,)

    def describe(self) -> str:
        return f"放 {KIND_LABELS.get(self.kind, self.kind)} → {_fmt(self.dest)}"


@dataclass(frozen=True, slots=True)
class MoveMove(Move):
    """移动一枚已入场的棋。"""

    player: int
    src: Pos
    dest: Pos
    #: 虫种 —— 只给视图选素材用
    kind: str = field(default="", compare=False, repr=False)
    #: 途经的每一格（含 ``dest``，不含 ``src``）—— 只给视图播滑行动画
    path: tuple[Pos, ...] = field(default=(), compare=False, repr=False)
    #: 出发 / 落点所在的**层号**（地面 = 0）—— 只给视图画爬升与下降
    from_height: int = field(default=0, compare=False, repr=False)
    to_height: int = field(default=0, compare=False, repr=False)

    def destinations(self) -> tuple[Pos, ...]:
        return (self.dest,)

    def describe(self) -> str:
        name = KIND_LABELS.get(self.kind, "棋子")
        if self.from_height or self.to_height:
            return f"{name} {_fmt(self.src)} → {_fmt(self.dest)}（{self.from_height}→{self.to_height} 层）"
        return f"{name} {_fmt(self.src)} → {_fmt(self.dest)}"


@dataclass(frozen=True, slots=True)
class PillbugMove(Move):
    """鼠妇的搬运着法：抬起一枚相邻的棋，放到自己邻边的空地。

    搬运时**鼠妇自己不挪窝**，所以生成器始终把 ``dest`` 填成 ``src``。
    ``carried`` / ``carried_dest`` 也参与 ``==`` —— 它们是这一手的**身份**，
    少一个字段就变成另一手棋了。
    """

    player: int
    src: Pos
    dest: Pos
    carried: Pos
    carried_dest: Pos
    #: 只给视图用
    carried_kind: str = field(default="", compare=False, repr=False)
    carried_owner: int = field(default=0, compare=False, repr=False)

    def destinations(self) -> tuple[Pos, ...]:
        """只有**被搬的那枚棋**换了位置。

        鼠妇原地不动，所以这里刻意**不**返回 ``dest``（它等于 ``src``）——
        ``destinations()`` 的语义是"这一手之后哪几格的内容变了"，视图拿的是
        走完之后的局面，把没动的格子也算进去会点亮错误的格子。
        """
        return (self.carried_dest,)

    def describe(self) -> str:
        return f"鼠妇 {_fmt(self.src)} 搬运 {_fmt(self.carried)} → {_fmt(self.carried_dest)}"


@dataclass(frozen=True, slots=True)
class PassMove(Move):
    """无处放子、也无棋可动时必须停一手。

    框架对"空着法表"的容忍度很差 —— MCTS 的 rollout 循环只拿 ``is_terminal()``
    当出口，``legal_moves`` 返回空表会一路索取到抛 ``RuntimeError``（AI 线程吞掉
    异常，表现成"AI 突然不下棋"）；minimax 则把空表当成"局面价值 0"。
    所以 :meth:`HiveGame.legal_moves` 在无处可走时**返回恰好一个 PassMove**，
    而不是空表。
    """

    player: int

    def destinations(self) -> tuple[Pos, ...]:
        return ()

    def describe(self) -> str:
        return "停一手（无处放子，也没有可动的棋）"
