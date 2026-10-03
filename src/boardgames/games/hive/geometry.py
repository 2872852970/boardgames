"""昆虫棋几何：**无边界**六边形网格的坐标与像素换算。

坐标约定
--------
* **pointy-top（尖顶）六边形** + **axial 坐标** ``(q, r)``。
* **没有棋盘边界** —— 蜂巢由已落棋子自己长出来，坐标是无限平面上的整数对。
  这是与大力士棋最本质的差别：``abalone.geometry`` 里那一整套"61 格常量表"
  （``CELLS`` / ``INDEX`` / ``NEIGHBORS`` / ``LINES`` / ``on_board``）在这里全部
  不存在，命中测试也**不做**边界校验（合法与否交给规则层判断"有没有邻子"）。
* 六个方向（下标与 :data:`DIRECTIONS` 一致）：

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

滑动门（Freedom to Move）
-------------------------
:data:`GATES` ``[d]`` 给出"从 ``src`` 往 ``d`` 方向走到 ``dst`` 时，被夹住的
那两个邻格"相对 ``src`` 的偏移。规则：这两个邻格都被占住时挤不过去。
可以自己验一下 —— ``d = 0``（E）时，``(0,0)`` 与 ``(1,0)`` 的共有邻格恰好是
``(1,-1)`` 与 ``(0,1)``，也就是 ``DIRECTIONS[1]`` 与 ``DIRECTIONS[5]``。

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

SQRT3 = math.sqrt(3.0)

#: 网格坐标（axial）
Pos = tuple[int, int]

#: 六个方向，下标见模块文档
DIRECTIONS: tuple[Pos, ...] = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
DIRECTION_NAMES: tuple[str, ...] = ("E", "NE", "NW", "W", "SW", "SE")
DIRECTION_COUNT = 6

#: ``GATES[d]`` = 从 ``src`` 沿 ``d`` 到 ``src + DIRECTIONS[d]`` 时，
#: 那两个"共有邻格"相对 ``src`` 的偏移（详见模块文档）。
GATES: tuple[tuple[Pos, Pos], ...] = tuple(
    (DIRECTIONS[(d + 1) % 6], DIRECTIONS[(d + 5) % 6]) for d in range(6)
)


def add(pos: Pos, direction: int) -> Pos:
    """沿方向 ``direction`` 走一格。"""
    dq, dr = DIRECTIONS[direction]
    return (pos[0] + dq, pos[1] + dr)


def offset(pos: Pos, delta: Pos) -> Pos:
    return (pos[0] + delta[0], pos[1] + delta[1])


def neighbors(pos: Pos) -> tuple[Pos, ...]:
    """六个相邻格（无限网格，永远返回 6 个）。"""
    q, r = pos
    return tuple((q + dq, r + dr) for dq, dr in DIRECTIONS)


def hex_distance(a: Pos, b: Pos) -> int:
    """两格之间的六边形（cube）距离。"""
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def are_adjacent(a: Pos, b: Pos) -> bool:
    return hex_distance(a, b) == 1


def axial_to_pixel(pos: Pos, size: float) -> tuple[float, float]:
    """axial 坐标 -> 像素（相对世界原点，``size`` = 六边形外接圆半径）。"""
    q, r = pos
    return (size * SQRT3 * (q + r / 2.0), size * 1.5 * r)


def pixel_to_axial(x: float, y: float, size: float) -> Pos:
    """像素 -> axial 坐标（cube round，含 half-up 舍入）。

    无限网格上没有"盘外"的概念，所以一定会返回一个合法坐标；是不是可落子的
    位置由规则层判断。
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
        (
            cx + size * math.cos(math.pi / 180.0 * (60 * i - 30)),
            cy + size * math.sin(math.pi / 180.0 * (60 * i - 30)),
        )
        for i in range(6)
    ]


def bounding_pixel_box(points: list[Pos], size: float) -> tuple[float, float, float, float]:
    """一组格坐标的像素包围盒 ``(left, top, right, bottom)``（相对世界原点）。

    六边形的宽是 ``√3 * size``、高是 ``2 * size``，中心之间有 ``1.5 * size``
    的行距，所以要在中心包围盒的基础上外扩半格。
    """
    if not points:
        half_w, half_h = SQRT3 * size / 2.0, size
        return (-half_w, -half_h, half_w, half_h)
    xs = [axial_to_pixel(pos, size) for pos in points]
    left = min(x for x, _ in xs) - SQRT3 * size / 2.0
    right = max(x for x, _ in xs) + SQRT3 * size / 2.0
    top = min(y for _, y in xs) - size
    bottom = max(y for _, y in xs) + size
    return (left, top, right, bottom)
