"""昆虫棋的局面：无边界蜂巢 + 叠层 + 手牌。

为什么不能用"一格一个 int"的扁平模型
--------------------------------------
大力士棋与四子棋都是一个定长 ``tuple[int, ...]``（61 / 42 格），因为棋盘是
固定大小的。昆虫棋两点都不同：

1. **无边界** —— 棋盘由已落棋子长出来，坐标是无限平面上的整数对，
   所以用 ``Pos -> 栈`` 的映射，而不是定长数组。
2. **可叠层** —— 甲虫能爬到别的棋上面，一个坐标上可以堆多枚棋。
   因此值是 ``tuple[Piece, ...]``（底 → 顶），而不是单个 int。

**被压住的棋天然不可动、不可选**：能动的那枚永远是栈顶。
"被甲虫压住的格子在贴己方 / 贴敌方判定里算甲虫那一方的颜色"也自动成立 ——
只看 :meth:`HiveState.owner_at` 返回的栈顶归属即可，不需要任何特判。

手牌不冗余存储
--------------
手牌由"配额 − 盘上该玩家该虫种的数量"推导（:meth:`HiveState.hand`），
从根上杜绝"手牌与盘面不同步"这一整类 bug。

平移不变性
----------
蜂巢的整体平移是同一个局面（绝对坐标没有意义）。:meth:`zobrist_hash` 先做
平移归一化再哈希 —— 不归一化会让置换表与 MCTS 的节点复用全部失效，
甚至把不同局面误判成同一局面。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from boardgames.core.state import State
from boardgames.games.hive.geometry import Pos, neighbors
from boardgames.games.hive.pieces import Piece, counts

#: 硬性手数上限：到达即判和。保证 MCTS 的 rollout 在任何情况下都会收敛。
MAX_PLY = 400

#: 相对坐标的 canonical 写法（hashable）
StackTable = tuple[tuple[Pos, tuple[Piece, ...]], ...]


def pack(mapping: dict[Pos, tuple[Piece, ...]]) -> StackTable:
    """``Pos -> 栈`` 的字典 -> 按坐标字典序排定的不可变表（空栈丢弃）。"""
    return tuple(sorted((pos, pieces) for pos, pieces in mapping.items() if pieces))


def _canonical(stacks: StackTable) -> StackTable:
    """平移归一化：整体平移到"最左下的格在 ``(0, 0)``"。

    只做平移，不做 12 重二面体（旋转 / 镜像）归一化：第一枚棋被规则钉死在
    世界原点，实际不会发生平移漂移；而旋转等价只会让置换表少命中一次，
    不会判错。这层归一化本身是纯保险。
    """
    if not stacks:
        return ()
    min_q = min(pos[0] for pos, _ in stacks)
    min_r = min(pos[1] for pos, _ in stacks)
    if min_q == 0 and min_r == 0:
        return stacks
    return tuple(((q - min_q, r - min_r), pieces) for (q, r), pieces in stacks)


@dataclass(frozen=True)
class HiveState(State):
    """不可变的昆虫棋局面。"""

    #: 按 ``Pos`` 字典序排定的栈表；每栈自底向顶
    stacks: StackTable = ()
    #: 双方**已完成**的回合数（含停一手）—— 用来判"蜂后期限"
    played: tuple[int, int] = (0, 0)
    current: int = 0
    ply: int = 0
    #: 已经出现过的**规范化局面哈希**序列（三次重复判和）；纯历史量，不参与相等性
    seen: tuple[int, ...] = field(default=(), compare=False)
    #: 连续停一手的次数，达到 2 判和
    passes: int = 0
    #: 本局是否启用扩展虫（瓢虫 / 蚊子 / 鼠妇）
    expansion: bool = False
    #: 胜利的**玩家索引**（0 或 1，``None`` 表示还没人赢 / 和棋）
    #:
    #: 刻意**不叫** ``winner`` —— ``State.winner()`` 是 ABC 的抽象方法，
    #: 同名字段会把它遮蔽掉，引擎侧 ``state.winner()`` 就会拿到非可调用对象。
    winner_player: int | None = None
    #: 和棋（双方同时被围满 / 三次重复 / 连续停两手 / 到 MAX_PLY）
    drawn: bool = False

    #: 构造期建好的查询索引与手牌缓存（不参与相等性，也不出现在 ``repr`` 里）
    _index: dict[Pos, tuple[Piece, ...]] = field(
        default=None, init=False, compare=False, repr=False
    )
    _hands: tuple[dict[str, int], dict[str, int]] = field(
        default=None, init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        index = dict(self.stacks)
        object.__setattr__(self, "_index", index)
        quota = counts(self.expansion)
        hands: list[dict[str, int]] = []
        for player in (0, 1):
            left = dict(quota)
            for stack in index.values():
                for piece in stack:
                    if piece.owner == player:
                        left[piece.kind] -= 1
            hands.append(left)
        object.__setattr__(self, "_hands", (hands[0], hands[1]))

    # ------------------------------------------------------------------ #
    # State 协议
    # ------------------------------------------------------------------ #

    @property
    def current_player(self) -> int:
        return self.current

    def is_terminal(self) -> bool:
        """**O(1)** —— 只看两个缓存的标量。

        终局判定绝不能在这里跑一遍着法生成：它在 MCTS 的 rollout 循环里
        每一步都会被调用。胜负与和棋都在 :meth:`HiveGame.apply` 里算好存下。
        """
        return self.winner_player is not None or self.drawn

    def winner(self) -> int | None:
        return self.winner_player

    def zobrist_hash(self) -> int:
        """规范化局面的哈希（**含轮到谁**）。

        不含 ``ply`` / ``seen`` / ``passes`` 等历史量 —— 排除掉才能让不同
        到达路径上的同一局面命中同一个置换表条目。
        """
        return hash((_canonical(self.stacks), self.current))

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def stack_at(self, pos: Pos) -> tuple[Piece, ...]:
        """该格的整叠棋（底 → 顶）；空格返回空元组。"""
        return self._index.get(pos, ())

    def height(self, pos: Pos) -> int:
        """该格的棋子层数（0 = 空格）。"""
        return len(self._index.get(pos, ()))

    def top(self, pos: Pos) -> Piece | None:
        """该格最上层的那枚棋（只有它能被移动 / 选中）。"""
        stack = self._index.get(pos, ())
        return stack[-1] if stack else None

    def owner_at(self, pos: Pos) -> int | None:
        """该格在"贴己方 / 贴敌方"判定里算哪一方的颜色（= 栈顶归属）。

        甲虫爬到对方棋上之后，这一格就**算甲虫那一方**的颜色 —— 于是放置判定
        自动正确，不需要任何特判。
        """
        piece = self.top(pos)
        return piece.owner if piece is not None else None

    def occupied(self) -> tuple[Pos, ...]:
        """有棋的格子（已排序）。"""
        return tuple(pos for pos, _ in self.stacks)

    def occupancy(self) -> dict[Pos, int]:
        """``Pos -> 层数`` 的副本。着法生成的热路径上用它。"""
        return {pos: len(stack) for pos, stack in self.stacks}

    def tops(self) -> dict[Pos, Piece]:
        """``Pos -> 栈顶棋子`` 的副本。"""
        return {pos: stack[-1] for pos, stack in self.stacks}

    def queen_pos(self, player: int) -> Pos | None:
        """某方蜂后的位置；还没落盘返回 ``None``。"""
        for pos, stack in self.stacks:
            for piece in stack:
                if piece.owner == player and piece.kind == "queen":
                    return pos
        return None

    def has_queen(self, player: int) -> bool:
        return self.queen_pos(player) is not None

    def queen_surround(self, player: int) -> int:
        """某方蜂后六面里**已被占**的格数（0..6）。

        这就是胜负条本身（满 6 且轮次结算后即判负），UI 与评估都直接读它，
        免得各写一份"数邻居"的逻辑。蜂后还没落盘时返回 0。
        """
        queen = self.queen_pos(player)
        if queen is None:
            return 0
        return sum(1 for n in neighbors(queen) if n in self._index)

    def hand(self, player: int) -> dict[str, int]:
        """某方手牌余量（**副本**，调用方可随意改）。"""
        return dict(self._hands[player])

    def hand_left(self, player: int, kind: str) -> int:
        return self._hands[player].get(kind, 0)

    def hand_total(self, player: int) -> int:
        return sum(self._hands[player].values())

    def pieces_on_board(self, player: int) -> int:
        """盘上属于某方的棋子数（含被压住的）。"""
        return sum(
            1 for stack in self._index.values() for piece in stack if piece.owner == player
        )

    def movable_tops(self, player: int) -> tuple[Pos, ...]:
        """某方**可以尝试移动**的棋子位置（= 该方为栈顶的格）。

        是否真的能动还要过一体规则；这里只回答"它是不是被压住了"。
        """
        return tuple(
            pos
            for pos, stack in self.stacks
            if stack and stack[-1].owner == player
        )

    def with_mapping(self, mapping: dict[Pos, tuple[Piece, ...]], **changes) -> HiveState:
        """从一份 ``Pos -> 栈`` 映射造一个新局面（``apply`` 用）。"""
        return replace(self, stacks=pack(mapping), **changes)


def initial_state(expansion: bool = False, first_player: int = 0) -> HiveState:
    """空棋盘开局。

    第一枚棋固定落在世界原点 ``(0, 0)``（规则：第一枚放中央）。世界原点固定
    也让平移归一化在实战中永远是恒等操作。
    """
    state = HiveState(expansion=expansion, current=first_player)
    return replace(state, seen=(state.zobrist_hash(),))
