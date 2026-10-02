"""胜负判定。"""

from __future__ import annotations

from boardgames.games.quoridor.move import PawnMove


def test_initial_state_is_not_terminal(game, make_state):
    st = make_state()
    assert st.is_terminal() is False
    assert st.winner() is None


def test_reaching_goal_row_wins(game, make_state):
    st = make_state(p0=(4, 1), p1=(4, 7), current=0)
    nxt = game.apply(st, PawnMove((4, 1), (4, 0)))
    assert nxt.is_terminal() is True
    assert nxt.winner() == 0


def test_player2_wins_at_bottom_row(game, make_state):
    st = make_state(p0=(8, 8), p1=(4, 7), current=1)
    nxt = game.apply(st, PawnMove((4, 7), (4, 8)))
    assert nxt.winner() == 1


def test_jump_landing_on_goal_row_wins(game, make_state):
    """跳跃落到目标行同样算赢。"""
    st = make_state(p0=(4, 2), p1=(4, 1), current=0)
    jump = PawnMove((4, 2), (4, 0))
    assert jump in game.pawn_moves_for(st, 0)
    nxt = game.apply(st, jump)
    assert nxt.is_terminal() is True
    assert nxt.winner() == 0


def test_no_moves_after_terminal(game, make_state):
    st = make_state(p0=(4, 0), p1=(4, 1), current=0)
    assert st.is_terminal() is True
    assert game.legal_moves(st) == []
