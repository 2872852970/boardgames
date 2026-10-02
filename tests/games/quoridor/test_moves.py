"""着法生成、apply 与不可变性。"""

from __future__ import annotations

from boardgames.core.game import SearchOptions
from boardgames.games.quoridor.move import PawnMove, WallMove


def test_initial_pawn_moves(game, make_state):
    st = make_state()
    moves = game.pawn_moves_for(st, 0)
    assert {m.dst for m in moves} == {(4, 7), (3, 8), (5, 8)}


def test_apply_pawn_move_advances_turn(game, make_state):
    st = make_state()
    nxt = game.apply(st, PawnMove((4, 8), (4, 7)))
    assert nxt.pawns[0] == (4, 7)
    assert nxt.current == 1
    assert nxt.ply == 1
    # 原状态不被修改（不可变性）
    assert st.pawns[0] == (4, 8) and st.current == 0 and st.ply == 0


def test_apply_wall_decrements_and_blocks(game, make_state):
    st = make_state()
    nxt = game.apply(st, WallMove("h", 3, 3))
    assert nxt.walls_left == (9, 10)
    assert nxt.current == 1
    from boardgames.games.quoridor import geometry as geo

    assert geo.blocked_vertical(nxt.size, nxt.h_mask, 3, 3) is True
    assert geo.blocked_vertical(nxt.size, nxt.h_mask, 4, 3) is True
    assert st.walls_left == (10, 10)  # 原状态未变


def test_is_legal_requires_correct_pawn(game, make_state):
    st = make_state()
    assert game.is_legal(st, PawnMove((4, 7), (4, 6))) is False  # 起点不是自己的棋子
    assert game.is_legal(st, PawnMove((4, 8), (4, 7))) is True


def test_legal_moves_full_includes_walls(game, make_state):
    st = make_state()
    moves = game.legal_moves(st)
    kinds = {type(m).__name__ for m in moves}
    assert kinds == {"PawnMove", "WallMove"}
    assert len(moves) == 3 + 128


def test_search_options_prune_wall_branching(game, make_state):
    st = make_state()
    full = game.legal_moves(st)
    pruned = game.legal_moves(st, SearchOptions(max_branch=6, order=True))
    walls = [m for m in pruned if isinstance(m, WallMove)]
    assert len(walls) <= 6
    assert len(pruned) < len(full)
    # 裁剪后的着法必须依旧全部合法
    for m in pruned:
        assert game.is_legal(st, m)


def test_zobrist_hash_changes_with_state(game, make_state):
    st = make_state()
    a = game.apply(st, PawnMove((4, 8), (4, 7)))
    b = game.apply(st, WallMove("h", 3, 3))
    assert len({st.zobrist_hash(), a.zobrist_hash(), b.zobrist_hash()}) == 3
    # 内容相同的局面 → 哈希相同
    same = make_state()
    assert same.zobrist_hash() == st.zobrist_hash()
    # 仅切换行动方也会改变哈希（否则置换表会串味）
    assert st.with_current(1).zobrist_hash() != st.zobrist_hash()


def test_evaluate_is_zero_sum(game, make_state):
    st = make_state()
    assert game.evaluate(st, 0) == -game.evaluate(st, 1)


def test_evaluate_prefers_being_ahead(game, make_state):
    ahead = make_state(p0=(4, 4), p1=(4, 0), current=0)
    behind = make_state(p0=(4, 7), p1=(4, 0), current=0)
    assert game.evaluate(ahead, 0) > game.evaluate(behind, 0)


def test_rollout_games_always_terminate(game, make_state):
    """双方都用 rollout 策略时棋局必须收敛。

    回归用例：早期用"曼哈顿距离贪心"驱动 rollout 会来回振荡，
    棋局永远打不完（MCTS 的每次模拟也都会撞到深度上限）。
    """
    import random

    for seed in range(12):
        rng = random.Random(seed)
        state = make_state()
        plies = 0
        while not state.is_terminal() and plies < 400:
            state = game.apply(state, game.rollout_move(state, rng, None, None))
            plies += 1
        assert state.is_terminal(), f"seed={seed} 未收敛（已走 {plies} 步）"


def test_distance_field_matches_shortest_path(game, make_state):
    from boardgames.games.quoridor import geometry as geo

    for walls in ((), ((3, 3),), ((3, 3), (5, 5))):
        st = make_state(h=walls)
        field = geo.distance_field(st.size, st.h_mask, st.v_mask, 0)
        for y in range(st.size):
            for x in range(st.size):
                expected = geo.shortest_path(st.size, st.h_mask, st.v_mask, (x, y), 0)
                got = field[y * st.size + x]
                assert got == (-1 if expected is None else expected)
