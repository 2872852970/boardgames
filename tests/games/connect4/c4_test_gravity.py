"""重力落子：棋子必落该列最低空位，满列不可投。"""

from __future__ import annotations


def test_empty_board_all_columns_legal(game):
    state = game.initial_state()
    assert [m.col for m in game.legal_moves(state)] == [0, 1, 2, 3, 4, 5, 6]


def test_piece_falls_to_bottom(game, drop):
    state = game.initial_state()
    after = drop(game, state, 3)
    assert after.at(3, 0) == 1
    assert after.heights[3] == 1
    assert after.at(3, 1) == 0, "只落一枚，下一格必须还是空的"


def test_piece_stacks_on_top(game, drop):
    state = game.initial_state()
    state = drop(game, state, 2)   # 玩家 1 落 col2 -> row0
    state = drop(game, state, 3)   # 玩家 2 落 col3 -> row0
    state = drop(game, state, 4)   # 玩家 1 落 col4
    state = drop(game, state, 2)   # 玩家 2 落 col2 -> 堆在玩家 1 头上（row1）
    assert state.at(2, 0) == 1
    assert state.at(2, 1) == 2
    assert state.heights[2] == 2


def test_same_column_same_player_can_stack(game, drop):
    """隔一手再投同一列，堆上去的可以是同色（连子的常见形态）。"""
    state = game.initial_state()
    for col in (0, 6, 0):
        state = drop(game, state, col)
    assert state.at(0, 0) == 1
    assert state.at(0, 1) == 1


def test_full_column_is_not_legal(game):
    """6 行的小棋盘：填满一列后不能再投。"""
    small = type(game)(cols=4, rows=2)
    state = small.initial_state()
    for _ in range(2):
        move = next(m for m in small.legal_moves(state) if m.col == 0)
        state = small.apply(state, move)
    assert state.heights[0] == 2
    assert 0 not in [m.col for m in small.legal_moves(state)]
    assert 1 in [m.col for m in small.legal_moves(state)]


def test_moving_move_to_wrong_row_is_illegal(game):
    from boardgames.games.connect4.move import DropMove

    state = game.initial_state()
    # 悬空投子（第 3 行）不合法
    assert not game.is_legal(state, DropMove(col=0, row=3, player=0))
    # 只有最低空位（第 0 行）合法
    assert game.is_legal(state, DropMove(col=0, row=0, player=0))


def test_out_of_range_column_is_illegal(game):
    from boardgames.games.connect4.move import DropMove

    state = game.initial_state()
    assert not game.is_legal(state, DropMove(col=-1, row=0, player=0))
    assert not game.is_legal(state, DropMove(col=7, row=0, player=0))


def test_apply_rejects_illegal_move(game):
    from boardgames.games.connect4.move import DropMove

    state = game.initial_state()
    try:
        game.apply(state, DropMove(col=0, row=4, player=0))
    except ValueError:
        pass
    else:
        raise AssertionError("非法着法应当抛 ValueError")


def test_move_is_not_placement(game):
    """四子棋没有"放完退出放置模式"的语义。"""
    from boardgames.games.connect4.move import DropMove

    assert DropMove(col=0, row=0, player=0).is_placement is False


def test_drop_move_describe(game):
    from boardgames.games.connect4.move import DropMove

    assert "第 1 列" in DropMove(col=0, row=0, player=0).describe()
