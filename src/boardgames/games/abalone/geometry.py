"""大力士棋几何：六边形坐标、邻接、直线片段、axial ↔ 像素。

坐标约定
--------
* **pointy-top（尖顶）六边形** + **axial 坐标** ``(q, r)``。
* 棋盘是半径 ``BOARD_RADIUS = 4`` 的六边形，共 **61 格**。合法条件::

      max(|q|, |r|, |q + r|) <= 4

  （第三个量就是 cube 坐标的 ``-y``；cube 三元组为 ``(q, -q-r, r)``）。
* 行 ``r ∈ [-4, 4]``，行宽 ``9 - |r|`` = **5, 6, 7, 8, 9, 8, 7, 6, 5**。
* 六个方向（下标就是 :attr:`~boardgames.games.abalone.move.AbaloneMove.direction`）：

  ==========  ========  =============
  下标        名称      axial 增量
  ==========  ========  =============
  0           E         ``( 1,  0)``
  1           NE        ``( 1, -1)``
  2           NW        ``( 0, -1)``
  3           W         ``(-1,  0)``
  4           SW        ``(-1,  1)``
  5           SE        ``( 0,  1)``
  ==========  ========  =============

* **三条轴**：一条直线上的棋子总是沿某条轴排列 ——
  轴 0 = E/W，轴 1 = NE/SW，轴 2 = NW/SE。方向 ``d`` 与 ``d + 3`` 互为反向，
  所以 ``d % 3`` 就是它所在的轴。

像素换算（``size`` = 六边形外接圆半径 = 中心到顶点的距离）
---------------------------------------------------------
::

    x = size * √3 * (q + r / 2)
    y = size * 1.5 * r

反解用 cube round（redblobgames 的标准做法）。**舍入必须 half-up**
（``math.floor(v + 0.5)``）：Python 内置的 :func:`round` 是 banker's rounding，
恰好落在两格分界上的像素会跳到隔壁格子，表现为"这一格点不中"。
"""

from __future__ import annotations

import math

#: 棋盘半径（中心格到最外圈的距离）。半径 4 的六边形恰好 61 格。
BOARD_RADIUS = 4
SQRT3 = math.sqrt(3.0)

#: 棋盘坐标
Pos = tuple[int, int]

#: 六个方向，下标见模块文档
DIRECTIONS: tuple[Pos, ...] = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
DIRECTION_NAMES: tuple[str, ...] = ("E", "NE", "NW", "W", "SW", "SE")
DIRECTION_COUNT = 6

#: 三条轴（方向下标 ``d`` 所在轴 = ``d % 3``）
AXES: tuple[int, ...] = (0, 1, 2)


def on_board(q: int, r: int) -> bool:
    """该 axial 坐标是否在 61 格棋盘内。"""
    return max(abs(q), abs(r), abs(q + r)) <= BOARD_RADIUS


def _build_cells() -> tuple[Pos, ...]:
    out: list[Pos] = []
    for r in range(-BOARD_RADIUS, BOARD_RADIUS + 1):
        for q in range(-BOARD_RADIUS, BOARD_RADIUS + 1):
            if on_board(q, r):
                out.append((q, r))
    return tuple(out)


def _build_neighbors() -> tuple[tuple[int, ...], ...]:
    """``NEIGHBORS[格下标][方向]`` -> 邻格下标，出界为 ``-1``。"""
    out: list[tuple[int, ...]] = []
    for q, r in CELLS:
        row = []
        for dq, dr in DIRECTIONS:
            row.append(INDEX.get((q + dq, r + dr), -1))
        out.append(tuple(row))
    return tuple(out)


def _build_lines() -> tuple[tuple[tuple[Pos, ...], int], ...]:
    """所有长度 2 / 3 的**连续直线片段**（``(格坐标元组, 所在轴)``）。

    只沿轴的**正方向**生成一次，因此天然无重复 —— 朴素地"每颗子 × 3 轴 ×
    长度 1..3"会把单子重复生成三遍。
    """
    out: list[tuple[tuple[Pos, ...], int]] = []
    for axis in AXES:
        dq, dr = DIRECTIONS[axis]
        for q, r in CELLS:
            chain: list[Pos] = [(q, r)]
            cq, cr = q, r
            for _ in range(2):  # 最多再延两格 -> 长度 2 与 3
                cq += dq
                cr += dr
                if not on_board(cq, cr):
                    break
                chain.append((cq, cr))
                out.append((tuple(chain), axis))
    return tuple(out)


#: 61 个格子，按 ``r`` 升序、同 ``r`` 内 ``q`` 升序排定（下标即棋盘一维索引）
CELLS: tuple[Pos, ...] = _build_cells()
#: 坐标 -> 一维下标
INDEX: dict[Pos, int] = {pos: i for i, pos in enumerate(CELLS)}
CELL_COUNT = len(CELLS)
#: 邻接表；``NEIGHBORS[i][d] == -1`` 表示那个方向出界
NEIGHBORS: tuple[tuple[int, ...], ...] = _build_neighbors()
#: 长度 2 / 3 的连续直线片段（285 条）
LINES: tuple[tuple[tuple[Pos, ...], int], ...] = _build_lines()
#: 同一批片段的**下标**版本 —— 着法生成在热路径上，别每步再做 61 次字典查找
LINES_INDEX: tuple[tuple[tuple[int, ...], int], ...] = tuple(
    (tuple(INDEX[p] for p in cells), axis) for cells, axis in LINES
)
#: 离心度：中心 0，最外圈 4
RING: tuple[int, ...] = tuple(max(abs(q), abs(r), abs(q + r)) for q, r in CELLS)
#: 中心性（``BOARD_RADIUS - RING``），越大越靠中心
CENTER_SCORE: tuple[int, ...] = tuple(BOARD_RADIUS - ring for ring in RING)


def index_of(pos: Pos) -> int:
    """坐标 -> 下标；盘外坐标抛 :class:`KeyError`。"""
    return INDEX[pos]


def ring_of(pos: Pos) -> int:
    """离心度（0 = 正中心，4 = 最外圈）。"""
    return RING[INDEX[pos]]


def step(index: int, direction: int) -> int:
    """沿 ``direction`` 走一格；出界返回 ``-1``。"""
    return NEIGHBORS[index][direction]


def axis_of(direction: int) -> int:
    """方向所在的轴（0/1/2）。"""
    return direction % 3


def group_axis(group: tuple[int, ...]) -> int:
    """这组格子（**下标**）所在的轴（0/1/2）。

    单子没有"排列方向"的概念（六个方向对它来说都只是"目标格是否为空"），
    返回 ``-1``；不是一条连续直线也返回 ``-1``。
    """
    if len(group) == 1:
        return -1
    members = set(group)
    for axis in AXES:
        back = (axis + 3) % 6
        starts = [c for c in group if NEIGHBORS[c][back] not in members]
        if len(starts) != 1:
            continue
        cell = starts[0]
        count = 1
        while count < len(group):
            cell = NEIGHBORS[cell][axis]
            if cell not in members:
                break
            count += 1
        if count == len(group):
            return axis
    return -1


def axial_to_pixel(pos: Pos, size: float) -> tuple[float, float]:
    """axial 坐标 -> 像素（相对棋盘中心，``size`` = 六边形外接圆半径）。"""
    q, r = pos
    return (size * SQRT3 * (q + r / 2.0), size * 1.5 * r)


def direction_pixel(direction: int, size: float) -> tuple[float, float]:
    """方向下标 -> 相邻两格中心的像素位移（长度恒为 ``√3 * size``）。"""
    return axial_to_pixel(DIRECTIONS[direction], size)


def pixel_to_axial(x: float, y: float, size: float) -> Pos:
    """像素 -> axial 坐标（cube round，可能为盘外的坐标）。

    调用方需要用 :func:`on_board` 自行校验 —— ``board_area`` 比棋盘包围盒大一圈，
    命中测试一定会收到盘外的点。
    """
    fq = (SQRT3 / 3.0 * x - y / 3.0) / size
    fr = (2.0 / 3.0 * y) / size
    fs = -fq - fr
    q = int(math.floor(fq + 0.5))
    r = int(math.floor(fr + 0.5))
    s = int(math.floor(fs + 0.5))
    dq, dr, ds = abs(q - fq), abs(r - fr), abs(s - fs)
    if dq > dr and dq > ds:
        q = -r - s
    elif dr > ds:
        r = -q - s
    return (q, r)


def hex_points(center: tuple[float, float], size: float) -> list[tuple[float, float]]:
    """pointy-top 六边形的 6 个顶点（顺时针，0 号在右上）。

    顶点角度 ``60 * i - 30`` 度：于是上下各有一个尖角、左右是两条平边，
    宽度 ``√3 * size``、高度 ``2 * size``，与 :func:`axial_to_pixel` 一致。
    """
    cx, cy = center
    return [
        (cx + size * math.cos(math.pi / 180.0 * (60 * i - 30)),
         cy + size * math.sin(math.pi / 180.0 * (60 * i - 30)))
        for i in range(6)
    ]

#: 棋盘包围盒尺寸（单位：``size``）：宽 ``9√3``、高 14
BOARD_UNIT_W = 9.0 * SQRT3
BOARD_UNIT_H = 14.0
