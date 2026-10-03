"""六边形几何：格数、行宽、邻接、直线片段表、坐标 ↔ 像素往返。

``test_pixel_round_trip_is_exact`` 是整块渲染与点击命中的地基 —— 它一旦挂了，
表现就是"棋盘画歪了 / 某几格点不中"，而这类 bug 靠断言数据结构是抓不到的。
"""

from __future__ import annotations

import pytest

from boardgames.games.abalone.geometry import (
    BOARD_RADIUS,
    CELL_COUNT,
    CELLS,
    INDEX,
    LINES,
    LINES_INDEX,
    NEIGHBORS,
    RING,
    axial_to_pixel,
    group_axis,
    on_board,
    pixel_to_axial,
)


def test_board_has_61_cells():
    assert CELL_COUNT == 61
    assert len(CELLS) == len(set(CELLS)) == 61


def test_row_widths_are_5_to_9_to_5():
    widths = [sum(1 for _, r in CELLS if r == row) for row in range(-BOARD_RADIUS, BOARD_RADIUS + 1)]
    assert widths == [5, 6, 7, 8, 9, 8, 7, 6, 5]


def test_ring_counts():
    counts: dict[int, int] = {}
    for ring in RING:
        counts[ring] = counts.get(ring, 0) + 1
    assert counts == {0: 1, 1: 6, 2: 12, 3: 18, 4: 24}


def test_neighbor_counts():
    """外圈 6 个角只有 3 个邻居，外圈其余 18 个有 4 个，内部 37 个有 6 个。"""
    tally = {3: 0, 4: 0, 6: 0}
    for index in range(CELL_COUNT):
        degree = sum(1 for j in NEIGHBORS[index] if j >= 0)
        tally[degree] = tally.get(degree, 0) + 1
    assert tally == {6: 37, 4: 18, 3: 6}


def test_neighbors_are_symmetric_and_offboard_is_minus_one():
    for index in range(CELL_COUNT):
        for direction, j in enumerate(NEIGHBORS[index]):
            if j < 0:
                continue
            assert index in NEIGHBORS[j], f"{CELLS[index]} 的 {direction} 号邻居不互指"


@pytest.mark.parametrize("size", [48, 25, 64, 17])
def test_pixel_round_trip_is_exact(size):
    """全部 61 格：坐标 → 像素 → 坐标必须原样回来。"""
    for pos in CELLS:
        x, y = axial_to_pixel(pos, size)
        assert pixel_to_axial(x, y, size) == pos, f"{pos} 在 size={size} 下往返失败"


def test_pixel_to_axial_reports_offboard():
    # 棋盘正中心 -> 中心格
    assert pixel_to_axial(0.0, 0.0, 40) == (0, 0)
    # 往右走很远 -> 必然出界
    far = pixel_to_axial(40 * 20.0, 0.0, 40)
    assert not on_board(*far)


def test_lines_table_is_complete_and_unique():
    """长度 2/3 的连续片段共 285 条（每条轴 95 条），且没有重复。"""
    assert len(LINES) == 285
    assert len(set(LINES)) == 285
    assert len(LINES_INDEX) == 285
    lengths = {len(cells) for cells, _ in LINES}
    assert lengths == {2, 3}
    assert sum(1 for cells, _ in LINES if len(cells) == 2) == 3 * 52
    assert sum(1 for cells, _ in LINES if len(cells) == 3) == 3 * 43


def test_every_line_entry_is_really_a_line():
    for cells, axis in LINES:
        indices = tuple(INDEX[p] for p in cells)
        assert group_axis(indices) == axis, f"{cells} 声称在轴 {axis} 上，实际不是"


def test_group_axis_rejects_non_lines():
    assert group_axis((INDEX[(0, 0)],)) == -1  # 单子
    # 不相邻的两格
    assert group_axis((INDEX[(0, 0)], INDEX[(2, 0)])) == -1
    # 三格但不是一条直线（L 形）
    assert group_axis((INDEX[(0, 0)], INDEX[(1, 0)], INDEX[(1, 1)])) == -1
    # 同一轴上的三格
    assert group_axis((INDEX[(-2, 0)], INDEX[(-1, 0)], INDEX[(0, 0)])) == 0
    # 沿 NE（轴 1）相邻的两格
    assert group_axis((INDEX[(2, -3)], INDEX[(3, -4)])) == 1
    # 沿 NW（轴 2）相邻的两格
    assert group_axis((INDEX[(2, -3)], INDEX[(2, -4)])) == 2
