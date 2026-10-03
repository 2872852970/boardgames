"""三种官方起始布局的结构校验。

雏菊布局的定义特征是"每方两朵花"—— 一朵 = 一个中心格 + 它的 6 个邻居 = 7 子。
这条断言比"逐格比对坐标"更能抓住"抄错了一行"的 bug。
"""

from __future__ import annotations

import pytest
from aba_helpers import parse

from boardgames.games.abalone.geometry import INDEX, NEIGHBORS, Pos
from boardgames.games.abalone.layouts import (
    ABALONE_SETUPS,
    MARBLES_PER_PLAYER,
    WIN_OUT,
    setup_cells,
)
from boardgames.games.abalone.state import initial_state


def test_constants():
    assert WIN_OUT == 6
    assert MARBLES_PER_PLAYER == 14
    assert ABALONE_SETUPS == ("standard", "belgian_daisy", "german_daisy")


@pytest.mark.parametrize("setup", ABALONE_SETUPS)
def test_each_side_has_14_marbles(setup):
    p0, p1 = setup_cells(setup)
    assert len(p0) == len(p1) == MARBLES_PER_PLAYER
    assert set(p0) & set(p1) == set()
    assert all(pos in INDEX for pos in p0 + p1)


@pytest.mark.parametrize("setup", ABALONE_SETUPS)
def test_initial_state_matches(setup):
    state = initial_state(setup)
    assert state.marble_count() == (14, 14)
    assert state.out == (0, 0)
    assert state.ply == 0
    assert not state.is_terminal()


def test_standard_is_two_full_rows_plus_three():
    p0, _ = setup_cells("standard")
    rows: dict[int, set[int]] = {}
    for q, r in p0:
        rows.setdefault(r, set()).add(q)
    assert rows == {
        2: {-2, -1, 0},
        3: {-4, -3, -2, -1, 0, 1},
        4: {-4, -3, -2, -1, 0},
    }


@pytest.mark.parametrize("setup", ["belgian_daisy", "german_daisy"])
@pytest.mark.parametrize("side", [0, 1])
def test_daisy_layouts_are_two_flowers(setup, side):
    p0, p1 = setup_cells(setup)
    cells = p0 if side == 0 else p1
    members = {INDEX[pos] for pos in cells}
    centers = [i for i in members if all(j in members for j in NEIGHBORS[i])]
    assert len(centers) == 2, f"{setup} 的玩家 {side + 1} 不是两朵花"
    # 两个中心+各自的六个邻居，恰好 14 格且互不重叠
    covered: set[int] = set()
    for center in centers:
        flower = {center, *NEIGHBORS[center]}
        assert not (covered & flower), "两朵花重叠了"
        covered |= flower
    assert covered == members


def test_standard_draws_the_shape_we_expect():
    rows = [
        "OOOOO",       # r = -4
        "OOOOOO",      # r = -3
        "..OOO..",     # r = -2
        "........",    # r = -1
        ".........",   # r =  0
        "........",    # r = +1
        "..XXX..",     # r = +2
        "XXXXXX",      # r = +3
        "XXXXX",       # r = +4
    ]
    state = parse(rows)
    assert state.marble_count() == (14, 14)
    assert state.at((0, 4)) == 1  # 最下一行
    assert state.at((2, -4)) == 2  # 最上一行
    assert state.at((0, 0)) == 0  # 正中心空着


def test_unknown_setup_raises():
    with pytest.raises(KeyError):
        setup_cells("daisy_of_doom")

    from boardgames.games.abalone.rules import AbaloneGame

    with pytest.raises(ValueError):
        AbaloneGame("nope")


def _rot180(cells: tuple[Pos, ...]) -> set[Pos]:
    return {(-q, -r) for q, r in cells}


def _mirror_lr(cells: tuple[Pos, ...]) -> set[Pos]:
    """左右镜像：``(q, r) -> (-q - r, r)``，行号不变。"""
    return {(-q - r, r) for q, r in cells}


def test_side_relations_are_the_documented_ones():
    """标准布局的双方是**中心对称**；雏菊布局的双方是**左右镜像**。

    这看着像可以统一，其实不能：标准布局占满了两整行，而"整行的左右镜像还是
    它自己"，所以镜像根本换不出对方那一侧来。
    """
    p0, p1 = setup_cells("standard")
    assert _rot180(p0) == set(p1)
    assert _mirror_lr(p0) == set(p0)  # 整行结构对镜像不敏感

    for setup in ("belgian_daisy", "german_daisy"):
        p0, p1 = setup_cells(setup)
        assert _mirror_lr(p0) == set(p1), f"{setup} 的双方不是左右镜像"
        assert _rot180(p0) == set(p0), f"{setup} 的每一方应当自身中心对称"
