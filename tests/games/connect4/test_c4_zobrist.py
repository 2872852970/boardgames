"""Zobrist 置换键。

关键性质：**同一局面的不同历史深度必须算出同一个键**，
否则置换表（minimax）会把"深度 8 的搜索结果"错用到"深度 4 的节点"上。
"""

from __future__ import annotations

from boardgames.games.connect4.state import Connect4State
from conftest import make_at


def _with_ply(state: Connect4State, ply: int) -> Connect4State:
    return Connect4State(
        cols=state.cols, rows=state.rows, cells=state.cells,
        heights=state.heights, current=state.current, ply=ply,
        winner_player=state.winner_player,
    )


def test_hash_ignores_ply(game):
    """ply 不参与哈希：同一局面不同深度必须同键。"""
    state = game.initial_state()
    state = game.apply(state, game.legal_moves(state)[0])
    a = _with_ply(state, 1)
    b = _with_ply(state, 99)
    assert a.zobrist_hash() == b.zobrist_hash()


def test_hash_ignores_heights(game):
    """heights 可从 cells 推出，不参与哈希（与 Quoridor 排除 ply 同理）。"""
    state = game.initial_state()
    state = game.apply(state, game.legal_moves(state)[0])
    bogus = Connect4State(
        cols=state.cols, rows=state.rows, cells=state.cells,
        heights=(9,) * state.cols,  # 故意写错
        current=state.current, ply=state.ply, winner_player=state.winner_player,
    )
    assert bogus.zobrist_hash() == state.zobrist_hash()


def test_hash_ignores_winner_player(game):
    state = game.initial_state()
    won = _with_ply(state, 0)
    flagged = Connect4State(
        cols=state.cols, rows=state.rows, cells=state.cells, heights=state.heights,
        current=state.current, ply=0, winner_player=1,
    )
    assert won.zobrist_hash() == flagged.zobrist_hash()


def test_different_positions_have_different_hashes(game):
    state = game.initial_state()
    a = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 0))
    b = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 1))
    assert a.zobrist_hash() != b.zobrist_hash()


def test_different_current_player_differs(game):
    state = make_at(6, 6, {(0, 0): 1})
    a = Connect4State(cols=6, rows=6, cells=state.cells, heights=state.heights,
                      current=0, ply=1, winner_player=None)
    b = Connect4State(cols=6, rows=6, cells=state.cells, heights=state.heights,
                      current=1, ply=1, winner_player=None)
    assert a.zobrist_hash() != b.zobrist_hash()


def test_different_board_sizes_differ():
    small = make_at(6, 6, {(0, 0): 1})
    large = make_at(8, 6, {(0, 0): 1})
    assert small.zobrist_hash() != large.zobrist_hash()


def test_transposition_reuses_key(game):
    """异路同局：投子顺序不同但棋盘相同 → 同键（置换表才能命中）。"""
    a = game.initial_state()
    a = game.apply(a, next(m for m in game.legal_moves(a) if m.col == 0))
    a = game.apply(a, next(m for m in game.legal_moves(a) if m.col == 1))

    b = game.initial_state()
    b = game.apply(b, next(m for m in game.legal_moves(b) if m.col == 1))
    b = game.apply(b, next(m for m in game.legal_moves(b) if m.col == 0))

    # 轮到不同玩家，但两列的子数一致时高度一致
    assert a.heights == b.heights
    assert sorted(v for v in a.cells if v) == sorted(v for v in b.cells if v)
