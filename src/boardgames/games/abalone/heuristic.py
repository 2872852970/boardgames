"""大力士棋静态评估：推出数、中心性、凝聚度、边缘危险。

设计要点
--------
* **每一项都写成 ``w * (f(我方) - f(对方))``** —— 于是
  ``evaluate(s, 0) == -evaluate(s, 1)`` 由构造成立，不需要靠测试事后纠偏。
  反过来意味着**不能**有 tempo（节奏）项：大力士棋双方完全对称，先手优势已经
  体现在先落子上，再加一项只会破坏反对称（四子棋踩过同一口井）。
* **不要**再加一个线性的"边缘项"：``Σ ring`` 与 ``Σ(4 - ring)`` 只差一个常数，
  信息完全重复。这里的 ``w_abalone_danger`` 用的是 **ring 的平方**，才对"贴边"
  有额外的惩罚（贴得越近风险陡增，这正是被推挤的真实风险曲线）。
* 尺度：典型局面 ``|score| ≲ 450``，落在 MCTS ``tanh(score / 600)`` 的有效区间内。
  ``w_abalone_out`` 别调到 600 以上，否则 rollout 回报会全部饱和成 ±1。
"""

from __future__ import annotations

from collections.abc import Mapping

from boardgames.games.abalone.geometry import (
    CELL_COUNT,
    CENTER_SCORE,
    NEIGHBORS,
    RING,
)
from boardgames.games.abalone.state import EMPTY, AbaloneState

#: 终局分（与 quoridor / connect4 的 heuristic 保持一致，配套 minimax 的 mate 处理）
MATE = 100_000.0

DEFAULT_WEIGHTS: dict[str, float] = {
    # 推出子数差：主导项，一枚就是一个"半步胜利"
    "w_abalone_out": 220.0,
    # 中心性：越靠中心越难被推出去
    "w_abalone_center": 6.0,
    # 凝聚度：相邻同色对数，阵型越紧密越难被以多推少
    "w_abalone_cohere": 2.5,
    # 边缘危险：己方子离盘边的平方距离（带负号，见模块文档）
    "w_abalone_danger": 3.0,
}


def _build_pairs() -> tuple[tuple[int, int], ...]:
    """棋盘上所有**无序**相邻格对（每条边只出现一次）。"""
    out: list[tuple[int, int]] = []
    for i in range(CELL_COUNT):
        for j in NEIGHBORS[i]:
            if j > i:
                out.append((i, j))
    return tuple(out)


#: 凝聚度检测只数一次，别在 rollout 里被反复构造
PAIRS: tuple[tuple[int, int], ...] = _build_pairs()


def merged_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    out = dict(DEFAULT_WEIGHTS)
    for key, value in weights.items():
        if key in out:  # 其余棋类的权重（如 w_path）直接忽略
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                continue
    return out


def cohesion(state: AbaloneState, who: int) -> int:
    """``who``（棋子值 1/2）的相邻同色**无序**对数。"""
    cells = state.cells
    return sum(1 for i, j in PAIRS if cells[i] == who and cells[j] == who)


def evaluate(
    state: AbaloneState,
    player: int,
    weights: Mapping[str, float] | None = None,
) -> float:
    """以 ``player`` 为视角的评估分（越大越好）。

    必须满足 ``evaluate(s, 0) == -evaluate(s, 1)`` —— 有测试锁这条对称性，
    否则 minimax 会在双方都不占便宜的局面里乱选。
    """
    winner = state.winner_player
    if winner is not None:
        return MATE if winner == player else -MATE

    w = merged_weights(weights)
    me = player + 1
    opp = 3 - me
    cells = state.cells

    # ---- 推出子数差（主导项）----
    score = w["w_abalone_out"] * (state.out[player] - state.out[1 - player])

    # ---- 中心性 与 边缘危险（同一次遍历）----
    center = 0
    danger = 0
    for index, value in enumerate(cells):
        if value == EMPTY:
            continue
        ring = RING[index]
        if value == me:
            center += CENTER_SCORE[index]
            danger += ring * ring
        else:
            center -= CENTER_SCORE[index]
            danger -= ring * ring
    score += w["w_abalone_center"] * center
    score -= w["w_abalone_danger"] * danger

    # ---- 凝聚度 ----
    score += w["w_abalone_cohere"] * (cohesion(state, me) - cohesion(state, opp))

    return float(score)
