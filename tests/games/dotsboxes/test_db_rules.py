"""点格棋规则测试。

棋盘图辅助：用 ``(orient, row, col)`` 边坐标按需造已画边集合，
其余自动留空 —— 不手写大段边列表（极易抄错）。
"""

from __future__ import annotations

import pytest

from boardgames.games.dotsboxes.move import EdgeMove
from boardgames.games.dotsboxes.rules import DotsBoxesGame
from boardgames.games.dotsboxes.state import DotsBoxesState, initial_state


def make_state(
    size: int = 3,
    h_edges: set[tuple[int, int]] | None = None,
    v_edges: set[tuple[int, int]] | None = None,
    boxes: dict[tuple[int, int], int] | None = None,
    *,
    current: int = 0,
) -> DotsBoxesState:
    """按边坐标造局面（其余边留空）。

    * ``h_edges``：已画的水平边集合 ``{(row, col), ...}``
    * ``v_edges``：已画的垂直边集合 ``{(row, col), ...}``
    * ``boxes``：已占领的方格 ``{(row, col): 玩家索引 0/1}``
    """
    n = size
    # 集合里的边一律记为玩家 1 所画（owner=1）；测试主要关注合法性/终局/额外回合
    h = tuple(1 if (r, c) in (h_edges or set()) else 0 for r in range(n) for c in range(n - 1))
    v = tuple(1 if (r, c) in (v_edges or set()) else 0 for r in range(n - 1) for c in range(n))
    grid = n - 1
    box = [0] * (grid * grid)
    scores = [0, 0]
    for (r, c), owner in (boxes or {}).items():
        box[r * grid + c] = owner + 1
        scores[owner] += 1
    ply = sum(1 for x in h if x) + sum(1 for x in v if x)
    total_edges = n * (n - 1) * 2
    winner = None
    if ply >= total_edges and scores[0] != scores[1]:
        winner = 0 if scores[0] > scores[1] else 1
    return DotsBoxesState(
        size=n, h_edges=h, v_edges=v, boxes=tuple(box),
        scores=(scores[0], scores[1]), current=current, ply=ply,
        winner_player=winner,
    )


@pytest.fixture
def game() -> DotsBoxesGame:
    return DotsBoxesGame(size=3)


# --------------------------------------------------------------------------- #
# 基本着法
# --------------------------------------------------------------------------- #


def test_initial_move_count(game: DotsBoxesGame) -> None:
    """3×3 点阵 = 12 条边，全部可画。"""
    s = game.initial_state()
    assert len(game.legal_moves(s)) == 12


def test_cannot_redraw_edge(game: DotsBoxesGame) -> None:
    """同一条边不能画两次。"""
    s = make_state(3, h_edges={(0, 0)})
    move = EdgeMove(0, 0, 0, 0)
    assert not game.is_legal(s, move)
    # 其余 11 条仍可画
    assert len(game.legal_moves(s)) == 11


def test_apply_draws_edge(game: DotsBoxesGame) -> None:
    s = game.initial_state()
    nxt = game.apply(s, EdgeMove(0, 0, 0, 0))
    assert nxt.h_edges[nxt.h_index(0, 0)] == 1
    assert nxt.ply == 1
    assert nxt.current == 1  # 没封格，换人
    # 原状态不可变
    assert s.h_edges[s.h_index(0, 0)] == 0


def test_out_of_range_moves_are_illegal(game: DotsBoxesGame) -> None:
    s = game.initial_state()
    # 水平边 col 最大 = size-2
    assert not game.is_legal(s, EdgeMove(0, 0, 2, 0))
    # 垂直边 row 最大 = size-2
    assert not game.is_legal(s, EdgeMove(1, 2, 0, 0))
    # orient 只能 0/1
    assert not game.is_legal(s, EdgeMove(2, 0, 0, 0))


# --------------------------------------------------------------------------- #
# 封格与额外回合
# --------------------------------------------------------------------------- #


def test_closing_box_grants_extra_turn(game: DotsBoxesGame) -> None:
    """画满第四条边：占格 + 同玩家继续。"""
    # (0,0) 格的三条边已画好，只差右边那条垂直边
    s = make_state(
        3,
        h_edges={(0, 0), (1, 0)},      # 格(0,0)的顶与底
        v_edges={(0, 0)},               # 格(0,0)的左
        current=0,
    )
    move = EdgeMove(1, 0, 1, 0)        # 格(0,0)的右
    assert game.is_legal(s, move)
    nxt = game.apply(s, move)
    assert nxt.box_owner(0, 0) == 1     # 玩家 0 占格
    assert nxt.scores == (1, 0)
    assert nxt.current == 0             # 额外回合：还是玩家 0
    assert nxt.ply == 4


def test_no_box_no_extra_turn(game: DotsBoxesGame) -> None:
    """画边没封格 → 换对方。"""
    s = game.initial_state()
    nxt = game.apply(s, EdgeMove(1, 0, 2, 0))
    assert nxt.current == 1
    assert nxt.scores == (0, 0)


def test_edge_closes_two_boxes_at_once(game: DotsBoxesGame) -> None:
    """一条边同时封住两个格子（连击）：两格都归画边者。"""
    # 两个格子共享中间那条垂直边，各自另外三条边都已画好
    s = make_state(
        3,
        h_edges={(0, 0), (1, 0), (0, 1), (1, 1)},
        v_edges={(0, 0), (0, 2)},       # 左格的左、右格的右
        current=1,
    )
    move = EdgeMove(1, 0, 1, 1)         # 共享边
    nxt = game.apply(s, move)
    assert nxt.box_owner(0, 0) == 2
    assert nxt.box_owner(0, 1) == 2
    assert nxt.scores == (0, 2)
    assert nxt.current == 1             # 额外回合


# --------------------------------------------------------------------------- #
# 终局
# --------------------------------------------------------------------------- #


def test_game_ends_when_all_edges_drawn(game: DotsBoxesGame) -> None:
    """所有边画完即终局，格子多者胜。"""
    # 2×2 格：手工画满 12 条边，玩家 0 拿 3 格玩家 1 拿 1 格
    h = {(r, c) for r in range(3) for c in range(2)}
    v = {(r, c) for r in range(2) for c in range(3)}
    s = make_state(3, h_edges=h, v_edges=v,
                   boxes={(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 1})
    assert s.is_terminal()
    assert s.winner() == 0


def test_draw_when_scores_equal(game: DotsBoxesGame) -> None:
    """格子数打平 → 平局（winner 为 None 但终局）。"""
    h = {(r, c) for r in range(3) for c in range(2)}
    v = {(r, c) for r in range(2) for c in range(3)}
    s = make_state(3, h_edges=h, v_edges=v,
                   boxes={(0, 0): 0, (0, 1): 1, (1, 0): 0, (1, 1): 1})
    assert s.is_terminal()
    assert s.winner() is None


def test_terminal_state_has_no_moves(game: DotsBoxesGame) -> None:
    h = {(r, c) for r in range(3) for c in range(2)}
    v = {(r, c) for r in range(2) for c in range(3)}
    s = make_state(3, h_edges=h, v_edges=v)
    assert game.legal_moves(s) == []


# --------------------------------------------------------------------------- #
# 哈希一致性
# --------------------------------------------------------------------------- #


def test_zobrist_same_position_same_hash(game: DotsBoxesGame) -> None:
    """同一局面（不同构造路径）哈希相同。"""
    a = game.initial_state()
    b = initial_state(3)
    assert a.zobrist_hash() == b.zobrist_hash()

    # 走一步再"退回来"（重新构造）哈希复原
    s = game.initial_state()
    after = game.apply(s, EdgeMove(0, 0, 0, 0))
    rebuilt = make_state(3, h_edges={(0, 0)}, current=1)
    assert after.zobrist_hash() == rebuilt.zobrist_hash()


def test_zobrist_different_turn_different_hash(game: DotsBoxesGame) -> None:
    """同一盘面但轮到别人走，是**不同**局面（能封格时谁的先手天差地别）。"""
    edges_h = {(0, 0), (1, 0)}
    a = make_state(3, h_edges=edges_h, v_edges={(0, 0)}, current=0)
    b = make_state(3, h_edges=edges_h, v_edges={(0, 0)}, current=1)
    assert a.zobrist_hash() != b.zobrist_hash()


# --------------------------------------------------------------------------- #
# 评估反对称
# --------------------------------------------------------------------------- #


def test_evaluate_is_antisymmetric(game: DotsBoxesGame) -> None:
    """evaluate(s,0) == -evaluate(s,1)。"""
    import random

    rng = random.Random(7)
    s = game.initial_state()
    for _ in range(40):
        assert game.evaluate(s, 0) == pytest.approx(-game.evaluate(s, 1))
        if s.is_terminal():
            break
        moves = game.legal_moves(s)
        s = game.apply(s, rng.choice(moves))


def test_evaluate_prefers_winning(game: DotsBoxesGame) -> None:
    """占格多的评估分更高。"""
    h = {(r, c) for r in range(3) for c in range(2)}
    v = {(r, c) for r in range(2) for c in range(3)}
    win = make_state(3, h_edges=h, v_edges=v,
                     boxes={(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 1})
    lose = make_state(3, h_edges=h, v_edges=v,
                      boxes={(0, 0): 1, (0, 1): 1, (1, 0): 1, (1, 1): 0})
    assert game.evaluate(win, 0) > 0
    assert game.evaluate(lose, 0) < 0


# --------------------------------------------------------------------------- #
# 整局收敛
# --------------------------------------------------------------------------- #


def test_full_game_terminates(game: DotsBoxesGame) -> None:
    """随机 rollout 也要能稳定跑完一局，且格子总数守恒。"""
    import random

    rng = random.Random(42)
    s = game.initial_state()
    total_boxes = (s.size - 1) ** 2
    for _ in range(500):
        if s.is_terminal():
            break
        s = game.apply(s, game.rollout_move(s, rng))
    assert s.is_terminal()
    assert sum(s.scores) == total_boxes
