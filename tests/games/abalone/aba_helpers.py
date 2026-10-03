"""大力士棋测试的造局面工具。

**名字必须叫 ``aba_helpers`` 而不是 ``helpers``** —— pytest 会把每个测试目录都插进
``sys.path`` 且没有 ``__init__.py``，两个同名模块会互相覆盖
（``tests/ui/helpers.py`` 已经占用了 ``helpers`` 这个名字）。

局面按**坐标**构造最省事：``make_state({(q, r): 值})``，其余 61 格自动留空。
想画图时用 :func:`parse`，它接受 9 行（上 → 下）的 5-6-7-8-9-8-7-6-5 网格::

    parse([
        "OOOOO",
        "OOOOOO",
        "..OOO..",
        ".......",
        ".........",
        ".......",
        "..XXX..",
        "XXXXXX",
        "XXXXX",
    ])

行内第 i 个字符对应 ``q = max(-4, -4-r) + i``。``X`` = 玩家 1，``O`` = 玩家 2。
"""

from __future__ import annotations

from boardgames.games.abalone.geometry import BOARD_RADIUS, CELL_COUNT, INDEX, Pos
from boardgames.games.abalone.state import AbaloneState

_CHARS = {".": 0, "X": 1, "O": 2}
LEGAL_CHARS = frozenset(_CHARS)


def row_start(r: int) -> int:
    """行 ``r`` 的第一个 ``q``（行宽 ``9 - |r|``）。"""
    return max(-BOARD_RADIUS, -BOARD_RADIUS - r)


def make_state(
    pieces: dict[Pos, int],
    *,
    out: tuple[int, int] = (0, 0),
    current: int = 0,
    ply: int = 0,
) -> AbaloneState:
    """按坐标造局面：``{(q, r): 0/1/2}``，未提到的格子留空。

    ``out[p]`` 是"``p`` 已把对手推出盘外的子数"。
    """
    cells = [0] * CELL_COUNT
    for pos, value in pieces.items():
        if pos not in INDEX:
            raise ValueError(f"坐标 {pos} 不在棋盘内")
        cells[INDEX[pos]] = value
    return AbaloneState(
        cells=tuple(cells), out=out, current=current, ply=ply, winner_player=None
    )


def parse(rows: list[str], *, out: tuple[int, int] = (0, 0), current: int = 0) -> AbaloneState:
    """由 9 行棋盘图构造局面（上 → 下）。"""
    if len(rows) != 2 * BOARD_RADIUS + 1:
        raise ValueError(f"需要 {2 * BOARD_RADIUS + 1} 行，收到 {len(rows)}")
    cells = [0] * CELL_COUNT
    for index, line in enumerate(rows):
        r = index - BOARD_RADIUS
        chars = line.replace(" ", "")
        expected = 2 * BOARD_RADIUS + 1 - abs(r)
        if len(chars) != expected:
            raise ValueError(f"第 r={r} 行应为 {expected} 格，收到 {len(chars)}: {line!r}")
        start = row_start(r)
        for i, ch in enumerate(chars):
            cells[INDEX[(start + i, r)]] = _CHARS[ch]
    return AbaloneState(cells=tuple(cells), out=out, current=current, ply=0, winner_player=None)


def place(state: AbaloneState, pieces: dict[Pos, int]) -> AbaloneState:
    """在已有局面基础上改若干格（用于摆"中局"）。"""
    cells = list(state.cells)
    for pos, value in pieces.items():
        cells[INDEX[pos]] = value
    return AbaloneState(
        cells=tuple(cells),
        out=state.out,
        current=state.current,
        ply=state.ply,
        winner_player=state.winner_player,
    )
