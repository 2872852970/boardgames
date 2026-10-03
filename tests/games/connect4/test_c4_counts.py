"""局面统计：双方已落子数（侧栏"已落 N 子"直接用这两个数）。"""

from __future__ import annotations

from conftest import make_at

from boardgames.games.connect4.rules import Connect4Game


def test_empty_board_counts_zero(game: Connect4Game):
    """空盘不能报出"对手已落 42 子"（那其实是空格数）。"""
    state = game.initial_state()
    assert state.count_pieces() == (0, 0)


def test_counts_each_side_separately(game: Connect4Game):
    state = make_at(7, 6, {(0, 0): 1, (1, 0): 2, (1, 1): 1, (2, 0): 2, (2, 1): 2})
    assert state.count_pieces() == (2, 3)


def test_counts_follow_play(game: Connect4Game, drop):
    state = game.initial_state()
    for col in (3, 3, 3):
        state = drop(game, state, col)
    assert state.count_pieces() == (2, 1)
    assert sum(state.count_pieces()) == state.heights_total()


def test_counts_on_full_board(game: Connect4Game):
    """竖条纹填满：偶数列给玩家 1（4 列），奇数列给玩家 2（3 列）。"""
    pieces = {(c, r): (c % 2) + 1 for c in range(7) for r in range(6)}
    state = make_at(7, 6, pieces)
    assert state.count_pieces() == (24, 18)
    assert sum(state.count_pieces()) == state.cols * state.rows == state.heights_total()
