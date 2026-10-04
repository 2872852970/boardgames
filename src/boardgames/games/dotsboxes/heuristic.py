"""点格棋静态评估。

评估的核心信号来自**"还剩一条边就封口"的格子数（威胁格）**：这类格子
下一手就能被画边的人白拿，攻方想占、守方得防。其次是**已占领格数差**（material）。

权重全部可被侧栏覆盖（键名见 :data:`DEFAULT_WEIGHTS`）。
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from boardgames.games.dotsboxes.state import DotsBoxesState

#: 终局分（与其它棋类保持一致，配套 minimax 的 TT_MATE_GUARD）
MATE = 100_000.0

DEFAULT_WEIGHTS: dict[str, float] = {
    # 已占领格数差
    "w_dots_material": 40.0,
    # "还剩一条边即封口"的格子数差（当前手能白拿的 vs 对手能白拿的）
    "w_dots_threat": 30.0,
}


@lru_cache(maxsize=64)
def _box_edges(size: int) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """每个方格的四条边，按方格下标排列，元素 ``(orient, row, col)``。

    ``orient`` 0=水平 / 1=垂直；坐标是边的锚点（见 state.py）。
    """
    grid = size - 1
    out: list[tuple[tuple[int, int, int], ...]] = []
    for row in range(grid):
        for col in range(grid):
            out.append((
                (0, row, col),          # 顶
                (0, row + 1, col),      # 底
                (1, row, col),          # 左
                (1, row, col + 1),      # 右
            ))
    return tuple(out)


def _edge_drawn(state: DotsBoxesState, orient: int, row: int, col: int) -> bool:
    if orient == 0:
        return bool(state.h_edges[state.h_index(row, col)])
    return bool(state.v_edges[state.v_index(row, col)])


def _open_edges_for_box(
    state: DotsBoxesState, box_edges: tuple[tuple[int, int, int], ...]
) -> tuple[tuple[int, int, int], ...]:
    """某个格子还空着的边。"""
    return tuple(
        (o, r, c) for o, r, c in box_edges if not _edge_drawn(state, o, r, c)
    )


def edge_closes_boxes(state: DotsBoxesState, orient: int, row: int, col: int) -> tuple[tuple[int, int], ...]:
    """画这条边会封住哪些方格（每个元素是方格 ``(row, col)``）。"""
    grid = state.size - 1
    out: list[tuple[int, int]] = []
    if orient == 0:  # 水平边：上下各一个方格
        if row - 1 >= 0:
            out.append((row - 1, col))
        if row < grid:
            out.append((row, col))
    else:  # 垂直边：左右各一个方格
        if col - 1 >= 0:
            out.append((row, col - 1))
        if col < grid:
            out.append((row, col))
    return tuple(out)


def boxes_closed_by_move(state: DotsBoxesState, orient: int, row: int, col: int) -> tuple[tuple[int, int], ...]:
    """画这条边实际会封住（四条边将凑满）的方格。"""
    candidates = edge_closes_boxes(state, orient, row, col)
    out = []
    for br, bc in candidates:
        if state.is_box_closed(br, bc):
            continue
        # 模拟画上这条边后是否四条边都齐了
        box_edges = _box_edges(state.size)[state.box_index(br, bc)]
        open_edges = _open_edges_for_box(state, box_edges)
        remaining = [e for e in open_edges if e != (orient, row, col)]
        if not remaining:
            out.append((br, bc))
    return tuple(out)


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


def evaluate(
    state: DotsBoxesState,
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
        # 边画完但无人明确胜（格子数打平）→ 平局
        diff = state.scores[player] - state.scores[1 - player]
        return MATE if diff > 0 else (-MATE if diff < 0 else 0.0)

    w = merged_weights(weights)

    # ---- 已占领格数差 ----
    score = w["w_dots_material"] * (state.scores[player] - state.scores[1 - player])

    # ---- 威胁格（差一条边封口）----
    # 当前手能白拿的"剩一条边"格子数 vs 对手能白拿的。
    # 双方都有能力封口，但从 player 视角：player 的潜在收益为正、对手的为负。
    # 由于"剩一条边"的格子是谁都能封（谁画这条边就是谁的），真正有意义的是
    # **当前轮到谁走**：轮到 player，则这些格子大概率被 player 收走。
    # 这里做一个对称的近似：分别数"player 封口后得分"与"对手封口后得分"，
    # 用**当前手先拿**的节奏差来近似。
    edges = _box_edges(state.size)
    me_threat = 0
    opp_threat = 0
    for idx, box_edges in enumerate(edges):
        if state.boxes[idx] != 0:
            continue
        open_edges = _open_edges_for_box(state, box_edges)
        if len(open_edges) == 1:
            # 只剩一条边，谁画谁得。当前手是 player → 记 player 的优势
            if state.current == player:
                me_threat += 1
            else:
                opp_threat += 1
    score += w["w_dots_threat"] * (me_threat - opp_threat)

    return score
