"""合法着法生成：中心优先排序、以及**必须忽略** max_branch / include_walls。"""

from __future__ import annotations

from boardgames.core.game import SearchOptions
from boardgames.games.connect4.move import DropMove
from conftest import make_at


def test_all_columns_legal_on_empty_board(game):
    state = game.initial_state()
    assert [m.col for m in game.legal_moves(state)] == list(range(state.cols))


def test_full_column_is_excluded(game):
    small = type(game)(cols=4, rows=1)
    state = small.initial_state()
    state = small.apply(state, next(m for m in small.legal_moves(state) if m.col == 1))
    assert 1 not in [m.col for m in small.legal_moves(state)]
    assert 0 in [m.col for m in small.legal_moves(state)]


def test_order_puts_center_first(game):
    """``options.order=True`` 时中心列优先（经典四子棋启发式）。"""
    state = game.initial_state()
    moves = game.legal_moves(state, SearchOptions(order=True))
    assert moves[0].col == state.cols // 2


def test_order_is_symmetric_around_center(game):
    state = game.initial_state()
    cols = [m.col for m in game.legal_moves(state, SearchOptions(order=True))]
    assert cols == sorted(cols, key=lambda c: abs(2 * c - (state.cols - 1)))


def test_no_order_keeps_left_to_right(game):
    state = game.initial_state()
    cols = [m.col for m in game.legal_moves(state, SearchOptions(order=False))]
    assert cols == list(range(state.cols))


def test_max_branch_is_ignored(game):
    """分支因子本来就小于默认 max_branch，裁剪只会误伤。"""
    state = game.initial_state()
    for branch in (0, 1, 2, 3):
        moves = game.legal_moves(state, SearchOptions(max_branch=branch, order=False))
        assert len(moves) == state.cols, f"max_branch={branch} 时不该裁剪着法"


def test_include_walls_is_ignored(game):
    """``include_walls`` 是墙棋专属开关。

    minimax 会按 ``include_walls = ply < wall_depth`` 逐层关闭它；
    若四子棋把它当成"裁剪着法"，深度 ≥2 的节点就只剩一个着法，棋力直接崩。
    """
    state = game.initial_state()
    for flag in (True, False):
        moves = game.legal_moves(state, SearchOptions(include_walls=flag, order=False))
        assert len(moves) == state.cols, f"include_walls={flag} 时不该裁剪着法"


def test_include_special_is_ignored(game):
    """``include_special`` 对四子棋没有语义（没有跳跃 / 吃过路兵）。"""
    state = game.initial_state()
    a = game.legal_moves(state, SearchOptions(include_special=True, order=False))
    b = game.legal_moves(state, SearchOptions(include_special=False, order=False))
    assert a == b


def test_terminal_state_has_no_moves(game):
    state = make_at(6, 6, {(c, 0): 1 for c in range(4)})
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 4))
    assert game.legal_moves(won) == []


def test_drop_move_carries_row_and_player(game):
    """row / player 必须存在：视图靠它们定位动画与颜色。"""
    state = game.initial_state()
    move = game.legal_moves(state)[0]
    assert isinstance(move, DropMove)
    assert move.row == state.heights[move.col]
    assert move.player == state.current
    assert move.is_placement is False


def test_moves_are_hashable(game):
    """MCTS 用 ``node.children[move]``，着法必须可哈希。"""
    state = game.initial_state()
    moves = game.legal_moves(state)
    assert len(set(moves)) == len(moves)
    assert {m: 1 for m in moves}[moves[0]] == 1


def test_is_legal_accepts_generated_moves(game):
    state = game.initial_state()
    for move in game.legal_moves(state):
        assert game.is_legal(state, move)


def test_open_columns_matches_legal_moves(game):
    """未满列才是合法投子列（col0 只堆了 1 枚，仍未满）。"""
    state = make_at(7, 6, {(0, r): 1 for r in range(6)})  # col0 填满
    assert game.open_columns(state) == [1, 2, 3, 4, 5, 6]
    assert [m.col for m in game.legal_moves(state)] == [1, 2, 3, 4, 5, 6]


def test_move_hints_exposes_columns(game):
    state = game.initial_state()
    hints = game.move_hints(state)
    assert hints["columns"] == tuple(range(state.cols))
