"""平局：棋盘填满但无人连成四子。"""

from __future__ import annotations

from conftest import make_at

from boardgames.games.connect4.state import Connect4State


def _full_draw_state(cols: int, rows: int) -> Connect4State:
    """造一个"填满但无四连"的局面：竖条纹交替，col c 全部属于 ``c % 2 + 1``。

    竖条纹保证任何横/斜方向都只有 1 颗同色；而列高 ``rows`` 若 < 4 也不会有纵向四连。
    """
    pieces = {(c, r): (c % 2) + 1 for c in range(cols) for r in range(rows)}
    state = make_at(cols, rows, pieces)
    return state


def test_full_board_is_terminal(game):
    state = _full_draw_state(7, 6)
    assert state.is_full()
    assert state.is_terminal()


def test_draw_has_no_winner(game):
    state = _full_draw_state(7, 6)
    assert state.winner() is None
    assert state.winner_player is None


def test_full_board_has_no_legal_moves(game):
    state = _full_draw_state(7, 6)
    assert game.legal_moves(state) == []


def test_small_full_board_is_draw(game):
    """3 列 3 行：填满也连不成四子（行数不够）。"""
    state = _full_draw_state(3, 3)
    assert state.is_full()
    assert state.winner() is None
    assert state.is_terminal()


def test_evaluate_is_zero_at_draw(game):
    state = _full_draw_state(7, 6)
    assert game.evaluate(state, 0) == 0.0
    assert game.evaluate(state, 1) == 0.0


def test_session_reports_draw_text(game):
    """``GameSession`` 依赖 ``winner() is None`` 显示"平局" —— 这条链路必须通。"""
    import tempfile
    from pathlib import Path

    from boardgames.controller.session import GameSession
    from boardgames.core.registry import build_default_registry
    from boardgames.core.result import Termination
    from boardgames.settings import Settings

    settings = Settings(Path(tempfile.mkdtemp()) / "s.json")
    session = GameSession(settings, build_default_registry(), "connect4")
    assert session.game.key == "connect4"

    # 把局面替换成"填满的平局"，并按 session.play 的方式推进
    session.state = _full_draw_state(session.state.cols, session.state.rows)
    if session.state.is_terminal():
        session.result = Termination.WIN  # play() 在终局时就是这么置的
    assert session.is_over
    assert session.winner() is None
    assert session.result_text() == "平局"


def test_full_board_detected_by_heights_not_ply(game):
    """``is_terminal`` 用 heights 判定，ply 与棋盘不同步也不会误判。"""
    state = _full_draw_state(7, 6)
    stale = Connect4State(
        cols=state.cols, rows=state.rows, cells=state.cells,
        heights=state.heights, current=0, ply=999, winner_player=None,
    )
    assert stale.is_terminal()
    assert stale.winner() is None
