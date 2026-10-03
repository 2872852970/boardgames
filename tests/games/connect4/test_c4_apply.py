"""``apply`` 的不可变性与 winner 缓存。"""

from __future__ import annotations

from conftest import make_at


def test_apply_does_not_mutate_input(game):
    state = game.initial_state()
    before_cells = state.cells
    before_heights = state.heights
    before_ply = state.ply
    move = game.legal_moves(state)[0]
    after = game.apply(state, move)

    assert state.cells is before_cells, "入参的 cells 不能被改"
    assert state.heights is before_heights
    assert state.ply == before_ply
    assert state.winner_player is None
    assert after is not state


def test_apply_increments_ply_and_switches_player(game):
    state = game.initial_state()
    after = game.apply(state, game.legal_moves(state)[0])
    assert after.ply == state.ply + 1
    assert after.current == 1 - state.current
    assert after.current_player == 1 - state.current


def test_apply_updates_heights(game):
    state = game.initial_state()
    move = next(m for m in game.legal_moves(state) if m.col == 4)
    after = game.apply(state, move)
    assert after.heights[4] == 1
    assert after.heights[:4] == state.heights[:4]


def test_winner_is_cached_only_when_won(game):
    state = game.initial_state()
    after = game.apply(state, game.legal_moves(state)[0])
    assert after.winner_player is None, "还没赢就不该缓存"


def test_winner_cached_after_win(game):
    state = make_at(6, 6, {(c, 0): 1 for c in (0, 1, 2)})
    after = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 3))
    assert after.winner_player == 0


def test_winner_method_is_not_shadowed(game):
    """``winner_player`` 是字段、``winner()`` 是方法 —— 两者不能互相遮蔽。

    引擎侧（minimax / mcts）会直接调 ``state.winner()``，
    如果字段叫 ``winner`` 就会拿到非可调用对象。
    """
    state = make_at(6, 6, {(c, 0): 1 for c in (0, 1, 2, 3)})
    assert callable(state.winner)
    assert state.winner() is None
    assert state.winner_player is None


def test_winner_method_returns_cached_value(game):
    state = game.initial_state()
    after = game.apply(state, game.legal_moves(state)[0])
    assert after.winner() == after.winner_player


def test_opponent_property(game):
    state = game.initial_state()
    assert state.opponent == 1 - state.current


def test_undo_restores_previous_state(game):
    """悔棋依赖状态不可变：``before`` 必须不受 ``after`` 影响。"""
    before = game.initial_state()
    after = game.apply(before, game.legal_moves(before)[0])
    assert before.heights == (0,) * before.cols
    assert after.heights != before.heights
    assert sum(before.heights) == 0


def test_replaying_same_move_from_same_state_is_deterministic(game):
    """置换表 / 搜索树依赖"相同状态产生相同结果"。"""
    state = game.initial_state()
    move = next(m for m in game.legal_moves(state) if m.col == 2)
    a = game.apply(state, move)
    b = game.apply(state, move)
    assert a.cells == b.cells
    assert a.heights == b.heights
    assert a.zobrist_hash() == b.zobrist_hash()
