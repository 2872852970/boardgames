"""四方向四连判定。

局面用 :func:`make_at` 按**坐标**构造（其余格子自动填满，因此不会出现
"忘了补齐某一列"的悬空违规），再用「投最后一子」的方式验证 :func:`scan_win`
真的会判出来 —— 既测了静态判定，也测了 ``apply`` 里的增量扫描路径。
"""

from __future__ import annotations

from boardgames.games.connect4.state import scan_win
from conftest import make_at, make_state_with_winner


def test_horizontal_win_is_detected(game):
    """横向四连：底行 XXXX。"""
    state = make_at(6, 6, {(c, 0): 1 for c in range(4)})
    assert state.winner_player is None, "手搭局面不填 winner_player 缓存"
    assert scan_win(state.cells, state.cols, state.rows, 0, 3, 1)

    # 用 apply 走最后一步：col4 空着，投进去即成四
    fresh = make_at(6, 6, {(c, 0): 1 for c in (0, 1, 2)})
    after = game.apply(fresh, next(m for m in game.legal_moves(fresh) if m.col == 3))
    assert after.winner_player == 0
    assert after.is_terminal()
    assert after.winning_line() == ((0, 0), (1, 0), (2, 0), (3, 0))


def test_win_completing_in_the_middle_is_detected(game):
    """落点补上"中间那一子"的横四（``X.XX`` → 投中间变 ``XXXX``）。

    这条最容易写错：落点左右两侧的连子数必须**相加**再比较，
    各自独立判断的话这局永远判不出胜负。
    """
    state = make_at(6, 6, {(0, 0): 1, (2, 0): 1, (3, 0): 1})
    assert not state.is_terminal()
    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 1))
    assert after.winner_player == 0, "补中间子也应判胜"
    assert after.winning_line() == ((0, 0), (1, 0), (2, 0), (3, 0))


def test_vertical_win_is_detected(game):
    """纵向四连：col1 堆到 row2，再投一枚落到 row3 即成四。"""
    state = make_at(6, 6, {(1, r): 1 for r in range(3)})
    assert state.heights[1] == 3
    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 1))
    assert after.winner_player == 0
    assert after.winning_line() == ((1, 0), (1, 1), (1, 2), (1, 3))


def test_ascending_diagonal_is_detected(game):
    """↗ 斜四 (0,0) (1,1) (2,2) (3,3)。"""
    state = make_at(4, 4, {(r, r): 1 for r in range(4)})
    line = [(0, 0), (1, 1), (2, 2), (3, 3)]
    assert all(state.at(c, r) == 1 for c, r in line)
    assert scan_win(state.cells, state.cols, state.rows, 3, 3, 1)


def test_descending_diagonal_is_detected(game):
    """↘ 斜四 (0,3) (1,2) (2,1) (3,0)。"""
    state = make_at(4, 4, {(3 - r, r): 1 for r in range(4)})
    line = [(0, 3), (1, 2), (2, 1), (3, 0)]
    assert all(state.at(c, r) == 1 for c, r in line)
    assert scan_win(state.cells, state.cols, state.rows, 3, 0, 1)


def test_ascending_diagonal_detected_by_apply(game):
    """投最后子补上 (3,3) 时，apply 的增量扫描必须判出斜四。

    col3 先垫 3 颗（对手），于是落点正好是 (3,3)。
    """
    state = make_at(4, 4, {
        (0, 0): 1, (1, 1): 1, (2, 2): 1,
        (3, 0): 2, (3, 1): 2, (3, 2): 2,
    })
    assert state.heights == (1, 2, 3, 3)
    assert [state.at(c, c) for c in range(3)] == [1, 1, 1]
    assert state.at(3, 3) == 0
    assert state.winner_player is None

    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 3))
    assert after.at(3, 3) == 1
    assert after.winner_player == 0
    assert after.winning_line() == ((0, 0), (1, 1), (2, 2), (3, 3))


def test_player_two_can_win(game):
    state = make_at(6, 6, {(c, 0): 2 for c in (1, 2, 3)}, current=1)
    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 0))
    assert after.winner_player == 1
    assert after.winning_line() == ((0, 0), (1, 0), (2, 0), (3, 0))


def test_three_in_a_row_is_not_a_win(game):
    state = make_at(6, 6, {(c, 0): 1 for c in (1, 2, 3)})
    assert not state.is_terminal()
    assert state.winner() is None


def test_three_with_a_gap_is_not_a_win(game):
    """``XX.X`` 中间断开 —— 不算连四。"""
    state = make_at(6, 6, {(0, 0): 1, (1, 0): 1, (3, 0): 1})
    assert not state.is_terminal()


def test_five_in_a_row_still_counts(game):
    """五子连比四子更长，同样算赢（``winning_line`` 只返回其中连续四颗）。"""
    state = make_at(7, 6, {(c, 0): 1 for c in range(5)})
    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 5))
    assert after.winner_player == 0
    line = after.winning_line()
    assert line is not None and len(line) == 4
    assert all(after.at(c, 0) == 1 for c, _ in line)
    assert [c for c, _ in line] == [0, 1, 2, 3]


def test_cached_winner_state_is_terminal(game):
    state = make_state_with_winner("""
        .......
        .......
        .......
        .......
        .......
        XXXX...
    """, 0)
    assert state.is_terminal()
    assert state.winner() == 0


def test_terminal_state_has_no_legal_moves(game):
    from boardgames.games.connect4.move import DropMove

    state = make_state_with_winner("""
        .......
        .......
        .......
        .......
        .......
        XXXX...
    """, 0)
    assert game.legal_moves(state) == []
    assert not game.is_legal(state, DropMove(col=0, row=1, player=0))


def test_evaluate_returns_mate_at_terminal(game):
    from boardgames.games.connect4.heuristic import MATE

    state = make_state_with_winner("""
        .......
        .......
        .......
        .......
        .......
        XXXX...
    """, 0)
    assert game.evaluate(state, 0) == MATE
    assert game.evaluate(state, 1) == -MATE
