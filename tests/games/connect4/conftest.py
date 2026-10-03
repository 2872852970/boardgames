"""四子棋测试夹具。

局面用**棋盘图字符串**构造，比手推落子序列可靠得多：

* 空格 = ``.``（必须**从底部连续堆叠**，违反重力的写法会在 ``parse_board`` 里报错）
* 玩家 1 = ``X``，玩家 2 = ``O``

字符串**从上往下**写行（第一行是最上面一行），与看图一致。
例如下面这局是 6 列 2 行，最底行 ``OXOXXO.``，顶行 ``.X.X.O.``：

.. code-block:: text

    .X.X.O.
    OXOXXO.
"""

from __future__ import annotations

import pytest

from boardgames.games.connect4.rules import Connect4Game
from boardgames.games.connect4.state import Connect4State

_CHARS = {".": 0, "X": 1, "O": 2}


def parse_board(board: str, *, current: int = 0) -> tuple[int, int, tuple[int, ...], tuple[int, ...]]:
    """把棋盘图解析成 ``(cols, rows, cells, heights)``。

    只从 ``board`` 推断列数与行数（按第一行的宽度和行数）。
    """
    lines = [line for line in board.strip().splitlines() if line.strip()]
    # 去掉每行可能带的缩进
    lines = [line.strip() for line in lines]
    rows = len(lines)
    cols = max(len(line) for line in lines)
    if any(len(line) != cols for line in lines):
        raise ValueError(f"棋盘每行宽度必须一致: {lines}")
    # 从上往下写，因此要先反转让 row 0（最底行）在最后
    grid = [[_CHARS[ch] for ch in line] for line in reversed(lines)]

    cells = [0] * (cols * rows)
    heights = [0] * cols
    for r in range(rows):
        for c in range(cols):
            value = grid[r][c]
            cells[r * cols + c] = value
            if value:
                heights[c] = r + 1

    # 校验重力：每列必须从底连续堆到顶，不能有悬空的子
    for c in range(cols):
        seen_empty = False
        for r in range(rows):
            if cells[r * cols + c] == 0:
                seen_empty = True
            elif seen_empty:
                raise ValueError(f"第 {c} 列第 {r} 行悬空，违反重力规则")
    return cols, rows, tuple(cells), tuple(heights)


def make_state(board: str, *, current: int = 0) -> Connect4State:
    """由棋盘图构造局面。"""
    cols, rows, cells, heights = parse_board(board)
    return Connect4State(
        cols=cols,
        rows=rows,
        cells=cells,
        heights=heights,
        current=current,
        ply=sum(1 for v in cells if v),
        winner_player=None,
    )


def make_at(
    cols: int,
    rows: int,
    pieces: dict[tuple[int, int], int],
    *,
    fill: int = 0,
    current: int = 0,
) -> Connect4State:
    """按**坐标**构造局面：``{(col, row): 值}``，其余格子填 ``fill``（默认留空）。

    只需要写出关心的格子，剩余位置自动处理 —— 不会因为"忘了补齐某一列"而违反重力。

    例：造 (0,0) (1,1) (2,2) 三个 X、其余留空::

        state = make_at(4, 4, {(0, 0): 1, (1, 1): 1, (2, 2): 1})
    """
    cells = [fill] * (cols * rows)
    for (c, r), value in pieces.items():
        if not (0 <= c < cols and 0 <= r < rows):
            raise ValueError(f"坐标越界: ({c}, {r}) 不在 {cols}x{rows} 内")
        cells[r * cols + c] = value
    heights = []
    for c in range(cols):
        height = 0
        for r in range(rows):
            if cells[r * cols + c] != 0:
                height = r + 1
        heights.append(height)
    return Connect4State(
        cols=cols,
        rows=rows,
        cells=tuple(cells),
        heights=tuple(heights),
        current=current,
        ply=sum(1 for v in cells if v),
        winner_player=None,
    )


def make_raw(cols: int, rows: int, rows_spec: list[str], *, current: int = 0) -> Connect4State:
    """直接给每行的字符串（**从上往下**，第一行是最上面一行）。

    与 :func:`make_state` 一样会校验重力（每行宽度一致、每列从底连续堆叠），
    只是列数与行数由参数给定，而不是从图里推断 —— 适合构造又宽又扁的局面
    （比如斜四只需要 4 列 4 行，不必凑成标准 7×6）。
    """
    if len(rows_spec) != rows:
        raise ValueError(f"给了 {len(rows_spec)} 行，但 rows={rows}")
    grid = [[_CHARS[ch] for ch in line] for line in reversed(rows_spec)]
    if any(len(line) != cols for line in grid):
        raise ValueError(f"每行宽度必须是 {cols}: {rows_spec}")
    cells = [0] * (cols * rows)
    heights = [0] * cols
    for r in range(rows):
        for c in range(cols):
            cells[r * cols + c] = grid[r][c]
            if grid[r][c]:
                heights[c] = r + 1
    for c in range(cols):
        seen_empty = False
        for r in range(rows):
            if cells[r * cols + c] == 0:
                seen_empty = True
            elif seen_empty:
                raise ValueError(f"第 {c} 列第 {r} 行悬空，违反重力规则")
    return Connect4State(
        cols=cols,
        rows=rows,
        cells=tuple(cells),
        heights=tuple(heights),
        current=current,
        ply=sum(1 for v in cells if v),
        winner_player=None,
    )


def make_state_with_winner(board: str, who: int) -> Connect4State:
    """构造一个已经分出胜负的局面（``who`` 为 1/2）。"""
    cols, rows, cells, heights = parse_board(board)
    return Connect4State(
        cols=cols,
        rows=rows,
        cells=cells,
        heights=heights,
        current=0,
        ply=sum(1 for v in cells if v),
        winner_player=who,
    )


@pytest.fixture
def game() -> Connect4Game:
    return Connect4Game()


@pytest.fixture
def drop():
    """往指定列投一枚当前行动方的棋子，返回新局面。"""

    def _drop(game: Connect4Game, state: Connect4State, col: int) -> Connect4State:
        move = next(m for m in game.legal_moves(state) if m.col == col)
        return game.apply(state, move)

    return _drop
