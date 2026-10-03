"""昆虫棋的静态评估与权重。

硬性约束（与大力士棋同一套，测试会锁）
--------------------------------------
1. **反对称**：``evaluate(s, 0) == -evaluate(s, 1)``。做法是每一项都写成
   ``w * (f(我) - f(敌))``，并且**不留任何 tempo 项** —— 昆虫棋双方完全对称，
   没有"轮到谁走"的固有优势。
2. **终局返回 ±** :data:`MATE`，和棋返回 ``0.0``。
3. **尺度**：``|score| ≲ 450``。MCTS 用 ``tanh(score / 600)`` 把它压成 [-1,1]，
   尺度失控会让 rollout 的价值信号被 tanh 压平。
"""

from __future__ import annotations

from collections.abc import Mapping

from boardgames.games.hive.geometry import Pos, neighbors
from boardgames.games.hive.pieces import QUEEN
from boardgames.games.hive.state import HiveState

#: 终局分的绝对值（与 minimax 的 ``MATE`` 保持一致）
MATE = 100_000.0

#: 默认权重。键名**必须带 ``hive_`` 前缀** —— ``w_center`` 已经被四子棋占用，
#: 重名会让"调昆虫棋的权重"连带改掉别的棋类。
DEFAULT_WEIGHTS: dict[str, float] = {
    #: 敌后 / 己后 邻格被占数之差（0..6）。主导项：围捕进度就是胜负本身。
    "w_hive_surround": 40.0,
    #: 蜂后被压住（不能动）—— 近乎必败
    "w_hive_buried": 40.0,
    #: 蜂后是否已落盘（落盘才能走子）
    "w_hive_queen": 20.0,
    #: "自己是栈顶"的棋子数（被压住的棋等于废子）
    "w_hive_mobility": 5.0,
    #: 手牌余量（资源 / 灵活度）
    "w_hive_hand": 4.0,
    #: 己方棋贴敌后的数量差（进攻潜力）
    "w_hive_contact": 2.0,
    #: rollout 里"优先放置"的概率（不是评估权重，但走同一条权重通道）
    "p_hive_place": 0.55,
}

#: 只读的默认权重快照（``merged_weights`` 的基底）
_FALLBACK = dict(DEFAULT_WEIGHTS)


def merged_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    """把外部权重并进默认值，**忽略其它棋类的键**。

    ``Settings.weights()`` 会把所有棋类的权重一起塞进来（见
    ``settings.schema.WEIGHT_KEYS``），不认识的键直接丢掉。
    """
    if not weights:
        return dict(_FALLBACK)
    out = dict(_FALLBACK)
    for key, value in weights.items():
        if key in out:
            out[key] = float(value)
    return out


def _buried(state: HiveState, player: int, queen: Pos | None) -> int:
    """蜂后是否被压在下面（顶层的棋不是她本人）。"""
    if queen is None:
        return 0
    top = state.top(queen)
    if top is None:
        return 0
    return 0 if (top.owner == player and top.kind == QUEEN) else 1


def evaluate(
    state: HiveState, player: int, weights: Mapping[str, float] | None = None
) -> float:
    """以 ``player`` 为视角的静态评估分（越大越好）。"""
    if state.winner_player is not None:
        return MATE if state.winner_player == player else -MATE
    if state.drawn:
        return 0.0

    w = merged_weights(weights)
    opp = 1 - player
    occupied: set[Pos] = set(state.occupied())

    my_queen = state.queen_pos(player)
    opp_queen = state.queen_pos(opp)

    my_surround = sum(1 for n in neighbors(my_queen) if n in occupied) if my_queen else 0
    opp_surround = sum(1 for n in neighbors(opp_queen) if n in occupied) if opp_queen else 0

    my_mobile = 0
    opp_mobile = 0
    my_contact = 0
    opp_contact = 0
    for pos, stack in state.stacks:
        top = stack[-1]
        if top.owner == player:
            my_mobile += 1
            if opp_queen is not None and pos in neighbors(opp_queen):
                my_contact += 1
        else:
            opp_mobile += 1
            if my_queen is not None and pos in neighbors(my_queen):
                opp_contact += 1

    score = 0.0
    score += w["w_hive_surround"] * (opp_surround - my_surround)
    score += w["w_hive_buried"] * (_buried(state, opp, opp_queen) - _buried(state, player, my_queen))
    score += w["w_hive_queen"] * (
        (0 if my_queen is None else 1) - (0 if opp_queen is None else 1)
    )
    score += w["w_hive_mobility"] * (my_mobile - opp_mobile)
    score += w["w_hive_hand"] * (state.hand_total(player) - state.hand_total(opp))
    score += w["w_hive_contact"] * (my_contact - opp_contact)
    return score
