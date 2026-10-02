"""Quoridor 测试公用夹具。"""

from __future__ import annotations

import pytest

from boardgames.games.quoridor.geometry import anchor_bit
from boardgames.games.quoridor.rules import QuoridorGame
from boardgames.games.quoridor.state import QuoridorState


@pytest.fixture
def game() -> QuoridorGame:
    return QuoridorGame()


@pytest.fixture
def make_state():
    """构造任意局面的工厂。

    ``h`` / ``v`` 传入锚点列表 ``[(ax, ay), ...]``。
    """

    def _make(
        *,
        size: int = 9,
        p0: tuple[int, int] = (4, 8),
        p1: tuple[int, int] = (4, 0),
        walls: tuple[int, int] = (10, 10),
        h: tuple[tuple[int, int], ...] = (),
        v: tuple[tuple[int, int], ...] = (),
        current: int = 0,
        ply: int = 0,
    ) -> QuoridorState:
        h_mask = 0
        v_mask = 0
        for ax, ay in h:
            h_mask |= anchor_bit(size, ax, ay)
        for ax, ay in v:
            v_mask |= anchor_bit(size, ax, ay)
        return QuoridorState(
            size=size,
            pawns=(tuple(p0), tuple(p1)),  # type: ignore[arg-type]
            walls_left=(walls[0], walls[1]),
            h_mask=h_mask,
            v_mask=v_mask,
            current=current,
            ply=ply,
        )

    return _make
