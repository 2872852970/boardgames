"""四子棋静态评估：子数、中心控制、连线长度、即时威胁。

设计要点
--------
* **窗口表**（所有长度 4 的连续格）预生成一次并缓存。``evaluate`` 在 MCTS 的
  rollout 里会被调用数十万次，表构造开销必须只付一次。
* **威胁检测**是棋力的主要来源："下一手就能连成四子"的列是最强的信号，
  攻方的要下、对方的必须堵。
* 权重全部可被侧栏覆盖（键名见 :data:`DEFAULT_WEIGHTS`）。
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from boardgames.games.connect4.state import CONNECT_TO, EMPTY, Connect4State

#: 终局分（与 quoridor/heuristic.py 保持一致，配套 minimax 的 TT_MATE_GUARD）
MATE = 100_000.0

DEFAULT_WEIGHTS: dict[str, float] = {
    # 子数差：每多一子 2 分
    "w_material": 2.0,
    # 中心列位置权重：中列比边列高约 51%
    "w_center": 8.0,
    # 四连通长度：活二 / 活三的潜在威胁
    "w_line": 12.0,
    # "下一手就能连成四子"的列数（进攻与防守共用，必须相等才对称）
    "w_threat": 60.0,
}

#: 连线长度 → 分数。**双方共用同一套**，否则 evaluate(s,0) != -evaluate(s,1)，
#: minimax 会在双方都不占便宜的局面里乱选。
LINE_SCORE: dict[int, float] = {2: 1.0, 3: 9.0}


@lru_cache(maxsize=64)
def center_weights(cols: int) -> tuple[float, ...]:
    """每列的位置权重：越靠中间越高（偶数列取中间两列）。"""
    if cols <= 1:
        return (1.0,)
    last = cols - 1
    return tuple(
        round(1.0 + 0.6 * (last - abs(2 * c - last)) / last, 4) for c in range(cols)
    )


@lru_cache(maxsize=64)
def windows(cols: int, rows: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    """所有长度 4 的连续格（每种方向各一条），坐标为 ``(col, row)``。"""
    out: list[tuple[tuple[int, int], ...]] = []
    # 横向
    for row in range(rows):
        for col in range(cols - CONNECT_TO + 1):
            out.append(tuple((col + i, row) for i in range(CONNECT_TO)))
    # 纵向
    for col in range(cols):
        for row in range(rows - CONNECT_TO + 1):
            out.append(tuple((col, row + i) for i in range(CONNECT_TO)))
    # 斜向（↗ 与 ↘）
    for row in range(rows - CONNECT_TO + 1):
        for col in range(cols - CONNECT_TO + 1):
            out.append(tuple((col + i, row + i) for i in range(CONNECT_TO)))
            out.append(tuple((col + i, row + CONNECT_TO - 1 - i) for i in range(CONNECT_TO)))
    return tuple(out)


def merged_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    out = dict(DEFAULT_WEIGHTS)
    for key, value in weights.items():
        if key in out:  # 其余游戏的权重（如 w_path）直接忽略
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                continue
    return out


def winning_columns(state: Connect4State, player: int) -> int:
    """有几列只要下一子就能立刻连成四子。

    判据：在该列的落点处模拟落子，扫描四个方向能否凑满 4 子。
    """
    who = player + 1
    total = 0
    for col in range(state.cols):
        row = state.heights[col]
        if row >= state.rows:
            continue
        if _connects_at(state, col, row, who):
            total += 1
    return total


def _connects_at(state: Connect4State, col: int, row: int, who: int) -> bool:
    """假设在 ``(col, row)`` 落下 ``who``，能否连成四子。

    落点所在格视为 ``who``（虚拟填入），其余空格仍是障碍 —— 不能假设同一轮里
    往别处再落子（重力下落且一手只投一枚）。
    """
    cells = state.cells
    cols, rows = state.cols, state.rows

    def value_at(rr: int, cc: int) -> int:
        if rr == row and cc == col:
            return who
        return cells[rr * cols + cc]

    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        for sign in (1, -1):
            step = 1
            while True:
                rr = row + dr * step * sign
                cc = col + dc * step * sign
                if not (0 <= rr < rows and 0 <= cc < cols):
                    break
                value = value_at(rr, cc)
                if value == who:
                    count += 1
                else:
                    break
                step += 1
        if count >= CONNECT_TO:
            return True
    return False


def evaluate(
    state: Connect4State,
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
    if state.is_full():
        return 0.0

    w = merged_weights(weights)
    me, opp = player + 1, 2 - player
    cols, rows = state.cols, state.rows
    cells = state.cells

    # ---- 子数差 ----
    mine = cells.count(me)
    theirs = cells.count(opp)
    score = w["w_material"] * (mine - theirs)

    # ---- 中心列控制 ----
    cw = center_weights(cols)
    for index, value in enumerate(cells):
        if value == EMPTY:
            continue
        weight = cw[index % cols]
        score += w["w_center"] * (weight if value == me else -weight)

    # ---- 连线长度（只看纯色窗口）----
    line_weight = w["w_line"]
    for window in windows(cols, rows):
        mine_count = 0
        theirs_count = 0
        for col, row in window:
            value = cells[row * cols + col]
            if value == me:
                mine_count += 1
            elif value == opp:
                theirs_count += 1
        # 混子窗口永远成不了线
        if mine_count and theirs_count:
            continue
        if mine_count >= 2:
            score += line_weight * LINE_SCORE.get(mine_count, 0.0)
        elif theirs_count >= 2:
            score -= line_weight * LINE_SCORE.get(theirs_count, 0.0)

    # ---- 即时威胁（双方同权，保证对称）----
    score += w["w_threat"] * (winning_columns(state, player) - winning_columns(state, 1 - player))

    # 刻意**没有** tempo（节奏）项：墙棋里"轮到谁走"有先后优势，
    # 四子棋没有 —— 先手优势已经体现在先落子的棋子上。再加一项反而会
    # 破坏 evaluate(s, 0) == -evaluate(s, 1) 的对称性。
    return score
