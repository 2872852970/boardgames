"""昆虫棋测试的造局面工具。

**名字必须叫 ``hive_build`` 而不是 ``helpers``** —— pytest 会把每个测试目录都插进
``sys.path`` 且没有 ``__init__.py``，两个同名模块会互相覆盖
（``tests/ui/helpers.py`` 已经占用了 ``helpers`` 这个名字）。

用法::

    make_state({
        (0, 0): [P(0, "queen")],
        (1, 0): [P(1, "ant"), P(1, "beetle")],   # 底 → 顶
    }, current=1, played=(1, 1))

``P`` 是 :func:`piece` 的简写。未提到的格子留空。

``played`` 默认为 ``(0, 0)``（双方都还没走满三个回合）—— 这样"蜂后期限"
不会意外生效；要测期限就显式传 ``played=(3, ...)``。
"""

from __future__ import annotations

from boardgames.games.hive.geometry import Pos, neighbors
from boardgames.games.hive.pieces import Piece
from boardgames.games.hive.state import HiveState, initial_state, pack

#: 简写：``P(0, "queen")``
P = Piece

#: 六个方向的下标（便于写"往 E 走一格"这类断言）
E, NE, NW, W, SW, SE = range(6)


def make_state(
    pieces: dict[Pos, list[Piece]] | None = None,
    *,
    current: int = 0,
    played: tuple[int, int] = (0, 0),
    ply: int = 0,
    expansion: bool = False,
    winner_player: int | None = None,
    drawn: bool = False,
) -> HiveState:
    """按坐标造局面。值是 ``Piece`` 列表，**自底向顶**。"""
    mapping: dict[Pos, tuple[Piece, ...]] = {}
    for pos, stack in (pieces or {}).items():
        mapping[pos] = tuple(stack)
    state = HiveState(
        stacks=pack(mapping),
        played=played,
        current=current,
        ply=ply,
        expansion=expansion,
        winner_player=winner_player,
        drawn=drawn,
    )
    return HiveState(
        stacks=state.stacks,
        played=state.played,
        current=state.current,
        ply=state.ply,
        seen=(state.zobrist_hash(),),
        expansion=state.expansion,
        winner_player=state.winner_player,
        drawn=state.drawn,
    )


def add(state: HiveState, pieces: dict[Pos, list[Piece]]) -> HiveState:
    """在已有局面上再加几枚棋（叠在同一格就变成更高的一层）。"""
    mapping = dict(state.stacks)
    for pos, stack in pieces.items():
        mapping[pos] = mapping.get(pos, ()) + tuple(stack)
    return HiveState(
        stacks=pack(mapping),
        played=state.played,
        current=state.current,
        ply=state.ply,
        seen=state.seen,
        passes=state.passes,
        expansion=state.expansion,
        winner_player=state.winner_player,
        drawn=state.drawn,
    )


def ring(pos: Pos, kind: str = "ant", owner: int = 1) -> dict[Pos, list[Piece]]:
    """``pos`` 六个邻格各放一枚 ``owner`` 的棋（用来构造"围死蜂后"）。"""
    return {n: [P(owner, kind)] for n in neighbors(pos)}


def surround(state: HiveState, pos: Pos, owner: int = 1) -> HiveState:
    """把一个格子的六个邻格补满 —— 蜂后被围满即判负。"""
    return add(state, ring(pos, owner=owner))


def fresh(expansion: bool = False) -> HiveState:
    return initial_state(expansion=expansion)


def placement_targets(game, state: HiveState) -> set[Pos]:
    """当前玩家所有合法**放置**落点。"""
    from boardgames.games.hive.move import PlaceMove

    return {m.dest for m in game.legal_moves(state) if isinstance(m, PlaceMove)}


def move_targets(game, state: HiveState, src: Pos) -> set[Pos]:
    """从 ``src`` 出发能落到的**移动**目标格。"""
    from boardgames.games.hive.move import MoveMove, PillbugMove

    return {
        m.dest
        for m in game.legal_moves(state)
        if isinstance(m, (MoveMove, PillbugMove)) and m.src == src
    }
