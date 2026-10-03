"""局面：叠层、手牌、平移归一化的哈希、终局判定的 O(1) 契约。"""

from __future__ import annotations

import pytest
from hive_build import P, make_state

from boardgames.games.hive import HiveGame
from boardgames.games.hive.move import PassMove
from boardgames.games.hive.state import MAX_PLY, initial_state, pack


def test_fresh_state_is_empty_and_black_to_move():
    state = initial_state()
    assert state.stacks == ()
    assert state.occupied() == ()
    assert state.current_player == 0
    assert state.ply == 0
    assert not state.is_terminal()
    assert state.winner() is None


def test_first_piece_targets_world_origin(game: HiveGame):
    """第一枚必须落在世界原点 —— 这条同时也是平移归一化在实战中恒等的原因。"""
    from boardgames.games.hive.move import PlaceMove

    state = initial_state()
    moves = game.legal_moves(state)
    assert moves
    assert all(isinstance(m, PlaceMove) and m.dest == (0, 0) for m in moves)


def test_height_top_and_owner_at():
    state = make_state({
        (0, 0): [P(1, "queen"), P(0, "beetle")],
        (1, 0): [P(0, "ant")],
    })
    assert state.height((0, 0)) == 2
    assert state.height((1, 0)) == 1
    assert state.height((9, 9)) == 0
    assert state.top((0, 0)) == P(0, "beetle")
    assert state.top((1, 0)) == P(0, "ant")
    assert state.top((9, 9)) is None
    # 被甲虫压住的格子，在"贴己方 / 贴敌方"里算**甲虫那一方**的颜色
    assert state.owner_at((0, 0)) == 0
    assert state.owner_at((1, 0)) == 0
    assert state.owner_at((9, 9)) is None


def test_stack_at_returns_bottom_to_top():
    state = make_state({(0, 0): [P(1, "queen"), P(1, "beetle"), P(0, "beetle")]})
    assert state.stack_at((0, 0)) == (P(1, "queen"), P(1, "beetle"), P(0, "beetle"))


def test_hand_is_derived_from_the_board():
    """手牌由"配额 − 盘上数量"推导，所以永远不可能与盘面不同步。"""
    state = make_state({
        (0, 0): [P(0, "queen")],
        (1, 0): [P(0, "ant"), P(0, "ant")],
        (2, 0): [P(1, "beetle")],
    })
    hand0 = state.hand(0)
    assert hand0["queen"] == 0
    assert hand0["ant"] == 1  # 3 - 2
    assert hand0["beetle"] == 2
    assert state.hand_left(0, "ant") == 1
    assert state.hand_total(0) == 0 + 2 + 3 + 2 + 1
    assert state.hand(1)["beetle"] == 1
    assert state.hand_total(1) == 10
    # 被压住的那枚也算"已落场"
    covered = make_state({(0, 0): [P(1, "queen"), P(0, "beetle")]})
    assert covered.hand(0)["beetle"] == 1
    assert covered.pieces_on_board(0) == 1


def test_hand_respects_the_expansion_switch():
    base = make_state({}, expansion=False)
    wide = make_state({}, expansion=True)
    assert base.hand_total(0) == 11
    assert wide.hand_total(0) == 14
    assert "ladybug" not in base.hand(0)
    assert wide.hand(0)["ladybug"] == 1


def test_queen_pos_and_has_queen():
    state = make_state({(0, 0): [P(0, "queen")], (3, -1): [P(1, "ant"), P(1, "queen")]})
    assert state.queen_pos(0) == (0, 0)
    assert state.queen_pos(1) == (3, -1)
    assert state.has_queen(0) and state.has_queen(1)
    bare = make_state({(0, 0): [P(0, "ant")]})
    assert bare.queen_pos(0) is None
    assert not bare.has_queen(0)
    assert bare.has_queen(1) is False


def test_movable_tops_excludes_covered_pieces():
    state = make_state({
        (0, 0): [P(1, "queen"), P(0, "beetle")],
        (1, 0): [P(0, "ant")],
        (2, 0): [P(1, "ant")],
    })
    # 蜂后被甲虫压住 —— 她不是栈顶，所以不在"可尝试移动"的名单里
    assert state.movable_tops(1) == ((2, 0),)
    assert set(state.movable_tops(0)) == {(0, 0), (1, 0)}


def test_apply_returns_a_new_object_and_never_mutates():
    """状态不可变是悔棋快照栈与 AI 搜索树的地基。"""
    game = HiveGame()
    state = initial_state()
    before_stacks = state.stacks
    before_occupied = state.occupied()
    move = game.legal_moves(state)[0]
    after = game.apply(state, move)
    assert after is not state
    assert state.stacks == before_stacks
    assert state.occupied() == before_occupied
    assert state.ply == 0
    assert after.ply == 1
    assert after.current_player == 1
    assert after.occupied() == ((0, 0),)


def test_pack_drops_empty_stacks_and_sorts():
    from boardgames.games.hive.pieces import Piece

    out = pack({(2, 0): (Piece(0, "ant"),), (0, 0): (), (1, 0): (Piece(1, "ant"),)})
    # 空栈必须被丢掉（否则"这里曾经有棋"会污染 frontier 与相邻判定）
    assert out == (((1, 0), (Piece(1, "ant"),)), ((2, 0), (Piece(0, "ant"),)))


def test_zobrist_is_translation_invariant():
    """蜂巢整体平移是**同一个局面** —— 不归一化会让置换表与 MCTS 节点复用全废。"""
    here = make_state({(0, 0): [P(0, "queen")], (1, 0): [P(1, "ant")]})
    shifted = make_state({(5, 3): [P(0, "queen")], (6, 3): [P(1, "ant")]})
    assert here.zobrist_hash() == shifted.zobrist_hash()
    assert here != shifted  # 坐标不同，对象本身当然不等


def test_zobrist_includes_whose_turn_it_is():
    """三次重复的规则是"含轮到谁"，所以换手必须换哈希。"""
    one = make_state({(0, 0): [P(0, "queen")]}, current=0)
    two = make_state({(0, 0): [P(0, "queen")]}, current=1)
    assert one.zobrist_hash() != two.zobrist_hash()


def test_zobrist_ignores_history_but_tracks_the_board():
    short = make_state({(0, 0): [P(0, "queen")]}, ply=1)
    long = make_state({(0, 0): [P(0, "queen")]}, ply=40)
    assert short.zobrist_hash() == long.zobrist_hash()
    other = make_state({(0, 0): [P(0, "beetle")]})
    assert other.zobrist_hash() != short.zobrist_hash()
    # 叠层顺序也要影响哈希（底层不同 = 局面不同）
    tall = make_state({(0, 0): [P(1, "queen"), P(0, "queen")]})
    assert tall.zobrist_hash() != short.zobrist_hash()


def test_is_terminal_is_o1_and_reads_no_move_generation(monkeypatch):
    """终局判定在 MCTS 的 rollout 循环里每一步都会调，绝不能跑一遍着法生成。"""
    game = HiveGame()
    state = game.initial_state()

    def boom(*args, **kwargs):  # pragma: no cover - 出错时才会执行
        raise AssertionError("is_terminal() 不该生成着法")

    monkeypatch.setattr(HiveGame, "legal_moves", boom)
    assert state.is_terminal() is False
    assert make_state({(0, 0): [P(0, "queen")]}, winner_player=0).is_terminal() is True
    assert make_state({(0, 0): [P(0, "queen")]}, drawn=True).is_terminal() is True


def test_winner_player_field_does_not_shadow_the_abc_method():
    """缓存胜者的字段只能叫 ``winner_player`` —— 叫 ``winner`` 会遮蔽 ABC 方法。"""
    state = make_state({(0, 0): [P(0, "queen")]}, winner_player=1)
    assert callable(state.winner)
    assert state.winner() == 1
    assert state.winner_player == 1


def test_winner_index_is_the_player_number_not_the_piece_value():
    """玩家号是 0/1，棋子值才是 1/2 —— 混用会让调色板索引直接 IndexError。"""
    state = make_state({(0, 0): [P(0, "queen")]}, winner_player=0)
    assert state.winner() == 0


def test_max_ply_constant_is_a_safety_net():
    assert MAX_PLY >= 100


def test_apply_rejects_a_move_from_the_wrong_player():
    game = HiveGame()
    state = initial_state()
    move = game.legal_moves(state)[0]
    forged = type(move)(1, move.kind, move.dest)
    with pytest.raises(ValueError):
        game.apply(state, forged)


def test_apply_rejects_moves_after_the_game_is_over():
    """终局之后再 apply 会静默地继续改变局面 —— 引擎里就是"赢了还在想"。"""
    game = HiveGame()
    state = make_state({(0, 0): [P(0, "queen")]}, winner_player=0)
    assert state.is_terminal()
    with pytest.raises(ValueError):
        game.apply(state, PassMove(0))
    with pytest.raises(ValueError):
        game.apply(make_state({(0, 0): [P(0, "queen")]}, drawn=True), PassMove(0))


def test_queen_surround_counts_occupied_neighbours_of_either_colour():
    """侧栏的"围 N/6"就是这个数 —— 敌我棋子都算，被压住的格子也算。（甲虫压头另算，见规则测试）"""
    from boardgames.games.hive.geometry import neighbors

    state = make_state({
        (0, 0): [P(0, "queen")],
        (1, 0): [P(0, "ant")],
        (-1, 0): [P(1, "beetle")],
        (0, 1): [P(1, "ant")],
    })
    assert state.queen_surround(0) == 3
    assert state.queen_surround(1) == 0, "玩家 2 的蜂后还没落盘"

    # 数满 6 面就该是终局 —— 这个数不能和规则层各算一份。
    # 按真实配额摆（3 兵蚁 + 2 蜘蛛 + 1 甲虫），免得手牌被摆成负数还看不出来。
    ring = dict(zip(neighbors((0, 0)),
                    ([P(1, "ant")], [P(1, "ant")], [P(1, "ant")],
                     [P(1, "spider")], [P(1, "spider")], [P(1, "beetle")]),
                    strict=True))
    full = make_state({(0, 0): [P(0, "queen")], **ring})
    assert full.queen_surround(0) == 6
    assert full.hand_total(1) == 5, "配额 11 − 上场 6"
