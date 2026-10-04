"""播棋（Mancala）的不可变局面。

拓扑约定
--------
标准 Kalah 规则：2 排 × 6 列共 12 个小坑，两端各一个**大坑（仓库）**。
每坑初始 4 枚种子（可调）。棋盘下标约定：

* ``pits``：长度 ``2 * pits_per_side``。前 ``pits_per_side`` 个是**玩家 0**
  的小坑（下标 0..P-1，方向从左到右）；后 ``pits_per_side`` 个是**玩家 1**
  的小坑（下标 P..2P-1）。玩家 0 的播种顺序沿下标**递增**（顺时针绕一圈），
  玩家 1 的播种顺序沿下标**递减**。
* ``stores``：长度 2，``stores[0]`` 是玩家 0 的仓库，``stores[1]`` 是玩家 1 的。

播种规则（Kalah 变体，也是用户描述的那套）：

* 从己方某个**非空**小坑取出全部种子，沿自己的方向**逐坑播一粒**，
  经过己方仓库时也播一粒，**跳过对手的仓库**。
* 若最后一粒落在**己方仓库** → **再走一手**（额外回合）。
* 若最后一粒落在**己方某个空坑** → 这一粒连同**正对面**对手坑里的种子，
  全部收进己方仓库（捕获）。
* 某方所有小坑清空时游戏结束，对手收走自己坑里剩余种子；仓库多者胜。
"""

from __future__ import annotations

from dataclasses import dataclass

from boardgames.core.state import State

#: 每侧小坑数（标准 Kalah）
DEFAULT_PITS = 6
#: 每坑初始种子数
DEFAULT_SEEDS = 4


@dataclass(frozen=True, slots=True)
class MancalaState(State):
    """一局播棋的局面。**不可变**。"""

    pits_per_side: int
    #: 12 个小坑的种子数（前 P 个玩家 0，后 P 个玩家 1）
    pits: tuple[int, ...]
    #: 两个仓库的种子数
    stores: tuple[int, int]
    current: int
    ply: int
    #: 获胜的玩家索引（0/1），未终局为 None；平局也是 None
    winner_player: int | None = None
    #: 是否已终局（含平局）。与 winner_player 区分开：平局时 winner 是 None
    #: 但游戏已经结束，不能继续着法生成（否则 MCTS 会向空着法表索取着法）。
    over: bool = False

    # ---- State 抽象 ----

    @property
    def current_player(self) -> int:
        return self.current

    def winner(self) -> int | None:
        return self.winner_player

    def is_terminal(self) -> bool:
        """某方小坑全空即终局（含平局）。O(1)：靠缓存字段。"""
        return self.over

    def zobrist_hash(self) -> int:
        # current / stores 都能从 pits 推出（stores 由捕获累积，但可由
        # 总种子数守恒推导部分信息；保守起见连同 current 一起参与哈希）
        return hash((self.pits_per_side, self.pits, self.stores, self.current))

    # ---- 便捷方法 ----

    def pit_range(self, player: int) -> range:
        """玩家 ``player`` 的小坑下标范围。"""
        p = self.pits_per_side
        if player == 0:
            return range(0, p)
        return range(p, 2 * p)

    def own_pits(self, player: int) -> tuple[int, ...]:
        """玩家 ``player`` 的非空小坑下标（按播种顺序）。"""
        p = self.pits_per_side
        if player == 0:
            return tuple(i for i in range(p) if self.pits[i] > 0)
        return tuple(i for i in range(2 * p - 1, p - 1, -1) if self.pits[i] > 0)

    def opposite(self, pit: int) -> int:
        """小坑正对面的对手坑下标（同一列，上下相差 ``p``）。

        屏幕布局（见 view）：下排从左到右是玩家 0 的坑 0..p-1，上排从左到右是
        玩家 1 的坑 p..2p-1 —— 同一列上下两坑的下标正好差 ``p``，捕获收的
        就是**正对面**那一坑。
        """
        p = self.pits_per_side
        return (pit + p) % (2 * p)

    def side_empty(self, player: int) -> bool:
        """玩家 ``player`` 这一侧的小坑是否全空。"""
        return all(self.pits[i] == 0 for i in self.pit_range(player))

    def total_seeds(self) -> int:
        return sum(self.pits) + sum(self.stores)


def sow_path(pits_per_side: int, start_pit: int, player: int, seeds: int) -> list[tuple[int, bool]]:
    """播种的落点序列，返回 ``(目标下标, 是否是仓库)`` 的列表。

    播种顺序（标准 Kalah，逆时针）：从 ``start_pit`` 出发，沿逆时针方向逐坑走
    ``seeds`` 步，每步播一粒。经过己方仓库时也占一步（播一粒进仓库），
    **跳过**对手仓库。

    逆时针槽位序列（``2p`` 个小坑 + 1 个己方仓库）：

    * 玩家 0：``0,1,...,p-1, store0, 2p-1,2p-2,...,p``
    * 玩家 1：``2p-1,2p-2,...,p, store1, 0,1,...,p-1``

    返回的每个元素 ``(idx, is_store)``：``idx`` 是小坑下标或仓库索引，
    ``is_store`` 为 True 时 ``idx`` 是玩家索引（0/1，即对应仓库）。
    """
    p = pits_per_side
    # 构造一个"槽位"循环序列，每个槽位是 (kind, index)，kind in {"pit", "store"}
    if player == 0:
        slots: list[tuple[str, int]] = []
        for i in range(0, p):
            slots.append(("pit", i))          # 己方坑 0..p-1
        slots.append(("store", 0))            # 己方仓库
        for i in range(2 * p - 1, p - 1, -1):
            slots.append(("pit", i))          # 对手坑 2p-1..p
    else:
        slots = []
        for i in range(2 * p - 1, p - 1, -1):
            slots.append(("pit", i))          # 己方坑 2p-1..p
        slots.append(("store", 1))            # 己方仓库
        for i in range(0, p):
            slots.append(("pit", i))          # 对手坑 0..p-1

    n = len(slots)  # 2p + 1
    # 找到起点 start_pit 在槽位序列中的位置
    start_pos = next(pos for pos, (kind, idx) in enumerate(slots) if kind == "pit" and idx == start_pit)

    out: list[tuple[int, bool]] = []
    for step in range(1, seeds + 1):
        kind, idx = slots[(start_pos + step) % n]
        out.append((idx, kind == "store"))
    return out


def lands_in_own_store(pits_per_side: int, start_pit: int, player: int, seeds: int) -> bool:
    """从 ``start_pit`` 播种，最后一粒是否落在己方仓库。"""
    if seeds <= 0:
        return False
    path = sow_path(pits_per_side, start_pit, player, seeds)
    last_idx, is_store = path[-1]
    return is_store


def initial_state(
    pits_per_side: int = DEFAULT_PITS,
    seeds_per_pit: int = DEFAULT_SEEDS,
    first_player: int = 0,
) -> MancalaState:
    p = int(pits_per_side)
    return MancalaState(
        pits_per_side=p,
        pits=(int(seeds_per_pit),) * (2 * p),
        stores=(0, 0),
        current=first_player,
        ply=0,
        winner_player=None,
    )
