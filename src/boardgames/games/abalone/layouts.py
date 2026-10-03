"""大力士棋的官方起始布局。

三种布局都用 ``(r, (q, ...))`` 的形式写成"每行占哪些格"，:func:`setup_cells`
再把它摊平成两份各 14 个坐标的元组。

* **standard（标准）** —— 己方底线两整行 + 中间突出 3 子。双方互为**中心对称**
  （180° 旋转 ``(q, r) -> (-q, -r)``），最均衡，适合新手。
* **belgian_daisy（比利时雏菊）** —— 每方两朵"雏菊"（中心格 + 它的 6 个邻居 = 7 子），
  靠外摆放，攻击性最强。
* **german_daisy（德国雏菊）** —— 同样是两朵雏菊，但整体内缩一行，更偏防守。

两个雏菊布局里，同一方的两朵花互为 180° 旋转；而**双方**之间是**左右镜像**
（``(q, r) -> (-q - r, r)``，保持行号不变、把该行的左右对调）。

标准布局**不能**用镜像描述 —— 它占满了两整行，而"整行的左右镜像还是它自己"，
镜像换不出对方那一侧来，必须用中心对称。两种关系都在测试里锁着。
"""

from __future__ import annotations

from boardgames.games.abalone.geometry import INDEX, Pos

#: 每方 14 子，被推出 6 子即负
MARBLES_PER_PLAYER = 14
#: 先把对手这么多子推出盘外即胜
WIN_OUT = 6

#: 布局键 -> 中文名（侧栏下拉用）
SETUP_LABELS: dict[str, str] = {
    "standard": "标准开局",
    "belgian_daisy": "比利时雏菊",
    "german_daisy": "德国雏菊",
}

ABALONE_SETUPS: tuple[str, ...] = ("standard", "belgian_daisy", "german_daisy")
DEFAULT_SETUP = "standard"

#: ``布局键 -> (玩家1 的行, 玩家2 的行)``，每行是 ``(r, (q, ...))``
_ROWS: dict[str, tuple[tuple[tuple[int, tuple[int, ...]], ...], ...]] = {
    "standard": (
        (
            (2, (-2, -1, 0)),
            (3, (-4, -3, -2, -1, 0, 1)),
            (4, (-4, -3, -2, -1, 0)),
        ),
        (
            (-4, (0, 1, 2, 3, 4)),
            (-3, (-1, 0, 1, 2, 3, 4)),
            (-2, (0, 1, 2)),
        ),
    ),
    "belgian_daisy": (
        (
            (-4, (3, 4)),
            (-3, (2, 3, 4)),
            (-2, (2, 3)),
            (2, (-3, -2)),
            (3, (-4, -3, -2)),
            (4, (-4, -3)),
        ),
        (
            (-4, (0, 1)),
            (-3, (-1, 0, 1)),
            (-2, (-1, 0)),
            (2, (0, 1)),
            (3, (-1, 0, 1)),
            (4, (-1, 0)),
        ),
    ),
    "german_daisy": (
        (
            (-3, (3, 4)),
            (-2, (2, 3, 4)),
            (-1, (2, 3)),
            (1, (-3, -2)),
            (2, (-4, -3, -2)),
            (3, (-4, -3)),
        ),
        (
            (-3, (-1, 0)),
            (-2, (-2, -1, 0)),
            (-1, (-2, -1)),
            (1, (1, 2)),
            (2, (0, 1, 2)),
            (3, (0, 1)),
        ),
    ),
}


def setup_cells(setup: str) -> tuple[tuple[Pos, ...], tuple[Pos, ...]]:
    """返回 ``(玩家1 的 14 个格, 玩家2 的 14 个格)``。

    未知布局抛 :class:`KeyError` —— 侧栏的 ``choice`` 已经把取值框住了，
    但构造 :class:`AbaloneGame` 时手滑写错要在第一时间炸出来。
    """
    if setup not in _ROWS:
        raise KeyError(f"未知的起始布局: {setup!r}（可选：{', '.join(ABALONE_SETUPS)}）")
    rows_p0, rows_p1 = _ROWS[setup]
    return (_flatten(rows_p0), _flatten(rows_p1))


def _flatten(rows: tuple[tuple[int, tuple[int, ...]], ...]) -> tuple[Pos, ...]:
    out: list[Pos] = []
    for r, qs in rows:
        for q in qs:
            pos = (q, r)
            if pos not in INDEX:
                raise ValueError(f"起始布局里出现了盘外坐标: {pos}")
            out.append(pos)
    return tuple(sorted(out))
