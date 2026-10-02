"""Quoridor 静态评估函数。

所有权重都可以被 AI 参数覆盖（键名见 :data:`DEFAULT_WEIGHTS`），
因此"评估权重可自定义"这一需求在这里落地。
"""

from __future__ import annotations

from collections.abc import Mapping

from boardgames.games.quoridor.geometry import distance_to_goal

#: 终局分（引擎会再按 ply 做"越早赢越好"的微调）。
MATE = 100_000.0

#: 评估权重默认值。
DEFAULT_WEIGHTS: dict[str, float] = {
    # 最短路径差：主导项，1 步 ≈ 100 分
    "w_path": 100.0,
    # 剩余墙数差：1 面墙 ≈ 0.4 步
    "w_walls": 40.0,
    # 机动性差（合法走子数量之差）
    "w_mobility": 6.0,
    # 节奏（轮到谁走）
    "w_tempo": 5.0,
    # 走子进度差（曼哈顿距离，弱项，用于打破平局）
    "w_progress": 3.0,
    # rollout 中以多大概率选择放墙（供 MCTS 使用）；放墙采样较贵，故不宜过高
    "p_wall": 0.08,
}


def merged_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    out = dict(DEFAULT_WEIGHTS)
    for k, v in weights.items():
        if k in out:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def evaluate(
    state,
    player: int,
    weights: Mapping[str, float] | None = None,
    *,
    pawn_move_counts: tuple[int, int] | None = None,
) -> float:
    """以 ``player`` 为视角的评估分（越大越有利于 ``player``）。

    ``pawn_move_counts`` 允许调用方传入预先算好的双方合法走子数以避免重复计算。
    """
    winner = state.winner()
    if winner is not None:
        return MATE if winner == player else -MATE

    w = merged_weights(weights)
    size, h, v = state.size, state.h_mask, state.v_mask
    me, opp = player, 1 - player

    # 用缓存的目标距离场（比每次重跑 BFS 快得多）
    d_me = distance_to_goal(size, h, v, state.pawns[me], state.goal_row(me))
    d_opp = distance_to_goal(size, h, v, state.pawns[opp], state.goal_row(opp))
    # 无路（理论上不会出现在合法局面）视为极差/极好
    inf = float(size * size)
    d_me = inf if d_me is None else float(d_me)
    d_opp = inf if d_opp is None else float(d_opp)

    score = w["w_path"] * (d_opp - d_me)
    score += w["w_walls"] * (state.walls_of(me) - state.walls_of(opp))

    if pawn_move_counts is not None:
        mob_me, mob_opp = pawn_move_counts
    else:  # 由调用方保证不触发（rules 会传入）
        mob_me = mob_opp = 0
    score += w["w_mobility"] * (mob_me - mob_opp)

    score += w["w_progress"] * (state.progress(opp) - state.progress(me))
    score += w["w_tempo"] * (1.0 if state.current == me else -1.0)
    return score
