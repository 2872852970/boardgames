"""无边界六边形网格的坐标与像素换算。

昆虫棋的几何与大力士棋共享同一套 axial 约定，但**没有棋盘边界** ——
所有"61 格常量表"都不存在，命中测试也不做边界校验。
"""

from __future__ import annotations

import builtins
import math

import pytest

from boardgames.games.hive.geometry import (
    DIRECTIONS,
    GATES,
    SQRT3,
    add,
    are_adjacent,
    axial_to_pixel,
    bounding_pixel_box,
    hex_distance,
    hex_points,
    neighbors,
    offset,
    pixel_to_axial,
)


def test_directions_form_a_closed_ring():
    """六个方向两两反向、和为 0 —— 否则网格会"走不回原地"。"""
    assert len(DIRECTIONS) == 6
    assert len(set(DIRECTIONS)) == 6
    for index, (dq, dr) in enumerate(DIRECTIONS):
        assert DIRECTIONS[(index + 3) % 6] == (-dq, -dr)
    assert sum(dq for dq, _ in DIRECTIONS) == 0
    assert sum(dr for _, dr in DIRECTIONS) == 0


def test_neighbors_are_six_distinct_cells():
    for pos in ((0, 0), (3, -2), (-7, 11)):
        ring = neighbors(pos)
        assert len(ring) == 6
        assert len(set(ring)) == 6
        assert pos not in ring
        assert all(are_adjacent(pos, n) for n in ring)
        assert set(ring) == {add(pos, d) for d in range(6)}


def test_gates_are_exactly_the_two_shared_neighbours():
    """``GATES[d]`` 必须正好是 ``src`` 与 ``src + DIRECTION[d]`` 的两个共有邻格。

    这是滑动门判定的基石 —— 差一个方向，整条 Freedom to Move 就歪了。
    """
    for pos in ((0, 0), (2, -3), (-5, 4)):
        for direction in range(6):
            dst = add(pos, direction)
            shared = set(neighbors(pos)) & set(neighbors(dst))
            gates = {offset(pos, g) for g in GATES[direction]}
            assert gates == shared, f"{pos} 方向 {direction}"
            assert len(gates) == 2


def test_hex_distance_and_adjacency():
    assert hex_distance((0, 0), (0, 0)) == 0
    assert hex_distance((3, -1), (3, -1)) == 0
    for direction in range(6):
        assert hex_distance((0, 0), add((0, 0), direction)) == 1
    assert are_adjacent((0, 0), (1, -1))
    assert not are_adjacent((0, 0), (2, -2))
    # 对称性
    for a, b in (((0, 0), (4, -3)), ((1, 2), (-3, 5)), ((0, 0), (0, 0))):
        assert hex_distance(a, b) == hex_distance(b, a)


def test_pixel_round_trip_over_a_large_disc():
    """axial -> 像素 -> axial 必须完全可逆（覆盖正负坐标与大范围）。"""
    size = 37.5
    for q in range(-12, 13):
        for r in range(-12, 13):
            x, y = axial_to_pixel((q, r), size)
            assert pixel_to_axial(x, y, size) == (q, r), f"({q},{r}) 往返失败"


def test_pixel_round_trip_is_exact_at_hex_centres():
    size = 64.0
    for pos in ((0, 0), (5, -3), (-9, 4), (11, 11)):
        x, y = axial_to_pixel(pos, size)
        assert pixel_to_axial(x, y, size) == pos


def test_pixel_to_axial_never_uses_builtin_round(monkeypatch):
    """**必须 half-up**（``math.floor(v + 0.5)``），不能用内置 :func:`round`。

    Python 内置 ``round`` 是银行家舍入：恰好落在两格分界上的像素会被舍到偶数格，
    表现为"这一格点不中"。这里直接把 ``round`` 换成炸弹，确保实现里没用到它。
    """

    def boom(*args, **kwargs):  # pragma: no cover - 只在出错时执行
        raise AssertionError("pixel_to_axial 用了内置 round（银行家舍入）")

    monkeypatch.setattr(builtins, "round", boom)
    pixel_to_axial(3.7, -2.1, 8.0)  # 只要不抛异常即可
    for q, r in ((0, 0), (3, -2), (-4, 5)):
        x, y = axial_to_pixel((q, r), 16.0)
        assert pixel_to_axial(x, y, 16.0) == (q, r)


def test_hex_points_shape():
    """pointy-top：宽度 ``√3 * size``、高度 ``2 * size``，且左右对称。"""
    size = 20.0
    points = hex_points((100.0, 50.0), size)
    assert len(points) == 6
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    assert max(xs) - min(xs) == pytest.approx(SQRT3 * size, rel=1e-9)
    assert max(ys) - min(ys) == pytest.approx(2.0 * size, rel=1e-9)
    assert min(xs) + max(xs) == pytest.approx(200.0, abs=1e-9)
    assert min(ys) + max(ys) == pytest.approx(100.0, abs=1e-9)
    # 上下各有一个尖角（y 的极值只出现一次）
    assert ys.count(min(ys)) == 1 and ys.count(max(ys)) == 1


def test_bounding_pixel_box_covers_every_centre():
    size = 12.0
    cells = [(0, 0), (3, -1), (-2, 4), (5, 5)]
    left, top, right, bottom = bounding_pixel_box(cells, size)
    for pos in cells:
        x, y = axial_to_pixel(pos, size)
        assert left < x < right
        assert top < y < bottom
    assert right - left > 0 and bottom - top > 0


def test_bounding_pixel_box_of_nothing_is_one_cell():
    left, top, right, bottom = bounding_pixel_box([], 10.0)
    assert right - left > 0 and bottom - top > 0
    assert left < 0 < right and top < 0 < bottom


def test_pixel_to_axial_is_actually_cube_round():
    """反解走的是 cube round：对大偏移也要落到最近格，而不是漂到隔壁。"""
    size = 10.0
    for pos in ((6, -2), (-7, 3), (0, 9)):
        cx, cy = axial_to_pixel(pos, size)
        # 在格子中心附近随机偏一点点，仍应命中同一格
        for dx in (-0.35, 0.0, 0.35):
            for dy in (-0.35, 0.0, 0.35):
                assert pixel_to_axial(cx + dx * size, cy + dy * size, size) == pos


def test_offset_and_math_helpers():
    assert offset((1, 2), (3, -5)) == (4, -3)
    assert math.floor(2.5 + 0.5) == 3  # half-up 与银行家舍入的分界
    assert round(2.5) == 2
