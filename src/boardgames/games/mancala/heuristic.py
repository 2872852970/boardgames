"""播棋静态评估。

Kalah 的胜负只由**最终仓库种子数**决定，评估的核心是**仓库种子差**
（material）。此外，**己方小坑里的种子是"未来的弹药"**，也要算进去；而
**额外回合**（最后一粒落己方仓库）与**捕获机会**是高价值信号，但为了严格
保持反对称，这里只采用与双方对称可得的量。

权重全部可被侧栏覆盖（键名见 :data:`DEFAULT_WEIGHTS`）。
"""

from __future__ import annotations

from collections.abc import Mapping

from boardgames.games.mancala.state import MancalaState, lands_in_own_store

#: 终局分（与其它棋类保持一致）
MATE = 100_000.0

DEFAULT_WEIGHTS: dict[str, float] = {
    # 仓库种子差
    "w_mancala_store": 10.0,
    # 己方小坑种子数（潜在弹药）差
    "w_mancala_pit": 3.0,
    # 额外回合机会：有多少个坑播完能落到己方仓库
    "w_mancala_turn": 6.0,
}


def merged_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    out = dict(DEFAULT_WEIGHTS)
    for key, value in weights.items():
        if key in out:
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                continue
    return out


def _turn_count(state: MancalaState, player: int) -> int:
    """玩家 ``player`` 有几个坑播完能获得额外回合。"""
    return sum(
        1
        for pit in state.pit_range(player)
        if lands_in_own_store(state.pits_per_side, pit, player, state.pits[pit])
    )


def evaluate(
    state: MancalaState,
    player: int,
    weights: Mapping[str, float] | None = None,
) -> float:
    """以 ``player`` 为视角的评估分（越大越好）。

    满足 ``evaluate(s, 0) == -evaluate(s, 1)``。
    """
    winner = state.winner_player
    if winner is not None:
        return MATE if winner == player else -MATE
    if state.is_terminal():
        # 终局但打平（仓库种子相等）
        return 0.0

    w = merged_weights(weights)
    opp = 1 - player

    # ---- 仓库种子差 ----
    score = w["w_mancala_store"] * (state.stores[player] - state.stores[opp])

    # ---- 己方小坑种子差（弹药）----
    my_pit = sum(state.pits[i] for i in state.pit_range(player))
    opp_pit = sum(state.pits[i] for i in state.pit_range(opp))
    score += w["w_mancala_pit"] * (my_pit - opp_pit)

    # ---- 额外回合机会差 ----
    score += w["w_mancala_turn"] * (_turn_count(state, player) - _turn_count(state, opp))

    return score
