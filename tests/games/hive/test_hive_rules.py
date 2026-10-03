"""昆虫棋规则：放置、六种走法、一体规则、滑动门、停一手、胜负。

每个用例都刻意造**最小**局面并把期望的落点集合写死 —— 规则里最容易错的
不是"能不能走"，而是"能走到哪几格"，写死集合才能抓到 off-by-one 与
坐标翻转这类 bug。
"""

from __future__ import annotations

import random

from hive_build import P, make_state, move_targets, placement_targets

from boardgames.core.game import SearchOptions
from boardgames.games.hive import HiveGame
from boardgames.games.hive.geometry import neighbors
from boardgames.games.hive.heuristic import DEFAULT_WEIGHTS
from boardgames.games.hive.move import MoveMove, PassMove, PillbugMove, PlaceMove
from boardgames.games.hive.rules import QUEEN_DEADLINE

# --------------------------------------------------------------------------- #
# 放置
# --------------------------------------------------------------------------- #


def test_second_piece_must_touch_the_first(game: HiveGame):
    """第二枚（对方的第一枚）必须贴上去 —— 此时还没有己方棋可贴。"""
    first = game.apply(game.initial_state(), PlaceMove(0, "ant", (0, 0)))
    assert placement_targets(game, first) == set(neighbors((0, 0)))


def test_new_pieces_touch_friends_and_never_enemies(game: HiveGame):
    """从第三枚起：至少贴一枚己方棋，且**不得贴任何敌方棋**。"""
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0)
    # (1,-1) 与 (0,1) 同时贴着双方 → 非法；(2,0) 一侧只贴敌方 → 非法
    assert placement_targets(game, state) == {(0, -1), (-1, 0), (-1, 1)}


def test_a_cell_covered_by_my_beetle_counts_as_my_colour(game: HiveGame):
    """甲虫压住对方棋子后，那一格在"贴己方 / 贴敌方"里算**甲虫那一方**的颜色。"""
    state = make_state(
        {(0, 0): [P(1, "ant")], (1, 0): [P(1, "ant"), P(0, "beetle")]},
        current=0,
    )
    targets = placement_targets(game, state)
    # (2,0) 只贴着 (1,0)，而 (1,0) 的栈顶是己方甲虫 → 合法
    assert (2, 0) in targets
    # 反过来，只贴着真正的敌方棋的格子仍然非法
    assert (0, -1) not in targets


def test_queen_deadline_forces_the_queen_out(game: HiveGame):
    """前三个回合都没放蜂后 → 第四个回合唯一的合法着法就是放蜂后。"""
    state = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]},
        current=0,
        played=(QUEEN_DEADLINE, 0),
    )
    moves = game.legal_moves(state)
    assert moves
    assert all(isinstance(m, PlaceMove) and m.kind == "queen" for m in moves)


def test_no_movement_before_your_own_queen_is_on_the_board(game: HiveGame):
    """自己的蜂后落下之前不能移动任何棋子。"""
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0)
    assert not [m for m in game.legal_moves(state) if isinstance(m, MoveMove)]

    with_queen = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")], (3, 0): [P(0, "queen")]},
        current=0,
    )
    assert [m for m in game.legal_moves(with_queen) if isinstance(m, MoveMove)]


# --------------------------------------------------------------------------- #
# 一体规则
# --------------------------------------------------------------------------- #


def test_the_bridge_piece_cannot_leave(game: HiveGame):
    """拿走会让蜂巢裂开的棋，一步都不能动。"""
    # (0,0) 是两块棋唯一的连接点，且这两块彼此不相邻
    state = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")], (-1, 0): [P(1, "ant")]},
        current=0,
    )
    assert move_targets(game, state, (0, 0)) == set()


def test_two_adjacent_neighbours_can_go_around_you(game: HiveGame):
    """恰好两个邻居、且这两个邻居彼此相邻 → 绕得过去，可以动。"""
    state = make_state(
        {
            (0, 0): [P(0, "ant")],
            (1, 0): [P(1, "ant")],
            (1, -1): [P(1, "ant")],
            (2, -1): [P(0, "queen")],  # 蜂后不在场就不能移动任何棋子
        },
        current=0,
    )
    assert move_targets(game, state, (0, 0))


# --------------------------------------------------------------------------- #
# 滑动门（Freedom to Move）
# --------------------------------------------------------------------------- #

# (1,0) 是 (0,0) 唯一的空邻格，而它与 (0,0) 共有的两个门格 (1,-1) / (0,1) 都被占
# 满 —— 谁都挤不过去。西侧那串棋的作用只是保证"拿走 (0,0) 之后蜂巢仍连通"，
# 这样用例测到的就纯粹是滑动门，而不是一体规则。
POCKET = {
    (0, 0): [P(0, "queen")],
    (1, -1): [P(1, "ant")],
    (0, -1): [P(1, "ant")],
    (-1, 0): [P(1, "ant")],
    (-1, 1): [P(1, "ant")],
    (0, 1): [P(1, "ant")],
}


def _pocket_mover(kind: str) -> dict:
    """把 (0,0) 换成 ``kind``，并把己方蜂后挪到环上（否则一个着法都生不出来）。"""
    board = dict(POCKET)
    board[(0, 0)] = [P(0, kind)]
    board[(-1, 0)] = [P(0, "queen")]
    return board


def test_a_ground_piece_cannot_squeeze_through_a_closed_gate(game: HiveGame):
    """地面棋：两个门格都被占 → 挤不过去。"""
    state = make_state(POCKET, current=0)
    assert move_targets(game, state, (0, 0)) == set()


def test_an_ant_is_blocked_by_the_same_gate(game: HiveGame):
    """兵蚁也走格子，门一样挡得住 —— 它绕不到里面去。"""
    pocket = dict(POCKET)
    pocket[(0, 0)] = [P(0, "ant")]
    pocket[(3, 0)] = [P(0, "queen")]  # 蜂后必须在场才允许移动
    state = make_state(pocket, current=0)
    assert move_targets(game, state, (0, 0)) == set()


def test_a_beetle_climbs_over_the_gate_but_still_cannot_squeeze(game: HiveGame):
    """甲虫按**层高**另算：门格只有 1 层时挡不住它上爬，但它同样挤不到空地。"""
    state = make_state(_pocket_mover("beetle"), current=0)
    targets = move_targets(game, state, (0, 0))
    # 五个 1 层棋堆都能爬上去……
    assert targets == {(1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)}
    # ……但唯一的空地 (1,0) 依然是关着的门
    assert (1, 0) not in targets


def test_beetle_carries_the_stack_height_for_the_animation(game: HiveGame):
    """爬升 / 下降的层号要带给视图，而且**不参与相等性**。"""
    state = make_state(_pocket_mover("beetle"), current=0)
    climb = next(
        m
        for m in game.legal_moves(state)
        if isinstance(m, MoveMove) and m.src == (0, 0) and m.dest == (0, -1)
    )
    assert climb.from_height == 0
    assert climb.to_height == 1
    # 视图只会构造 (player, src, dest)，必须和生成的这一手判等
    assert climb == MoveMove(0, (0, 0), (0, -1))


def test_a_beetle_on_top_is_always_free_to_move(game: HiveGame):
    """叠层豁免：栈顶那枚棋拿走不会断开蜂巢，所以永远允许尝试。"""
    state = make_state(
        {
            (0, 0): [P(0, "queen"), P(0, "beetle")],
            (1, 0): [P(1, "ant")],
            (-1, 0): [P(1, "ant")],
        },
        current=0,
    )
    # 底下的蜂后本身是连接点（会被一体规则钉死），甲虫压在她头上却能走
    climb = next(
        m for m in game.legal_moves(state) if isinstance(m, MoveMove) and m.src == (0, 0)
    )
    assert climb.from_height == 1


# --------------------------------------------------------------------------- #
# 蚱蜢 / 蜘蛛 / 兵蚁
# --------------------------------------------------------------------------- #

# 一条四格长的蜂巢：(0,0) 是主角，(3,0) 是己方蜂后（没有蜂后就不能移动）
LINE = {
    (0, 0): [P(0, "ant")],
    (1, 0): [P(1, "ant")],
    (2, 0): [P(1, "ant")],
    (3, 0): [P(0, "queen")],
}


def _swap_mover(mapping, kind: str) -> dict:
    out = dict(mapping)
    out[(0, 0)] = [P(0, kind)]
    return out


def test_grasshopper_jumps_in_a_straight_line_to_the_first_gap(game: HiveGame):
    state = make_state(_swap_mover(LINE, "grasshopper"), current=0)
    # 跳过 (1,0)(2,0)(3,0)，落在 (4,0)；空的那一侧方向没有可跳的棋
    assert move_targets(game, state, (0, 0)) == {(4, 0)}


def test_grasshopper_ignores_the_sliding_gate(game: HiveGame):
    """官方明确：蚱蜢是真的**跳过去**，不受滑动门限制。"""
    board = _swap_mover(LINE, "grasshopper")
    board[(1, -1)] = [P(1, "ant")]  # 正好是 (0,0)→(1,0) 的两个门格之一
    board[(0, 1)] = [P(1, "ant")]
    state = make_state(board, current=0)
    targets = move_targets(game, state, (0, 0))
    assert (4, 0) in targets  # 门关着也照跳
    assert (2, -2) in targets and (0, 2) in targets  # 门格本身成了起跳点


def test_spider_moves_exactly_three_cells(game: HiveGame):
    state = make_state(_swap_mover(LINE, "spider"), current=0)
    moves = [
        m
        for m in game.legal_moves(state)
        if isinstance(m, MoveMove) and m.src == (0, 0)
    ]
    assert {m.dest for m in moves} == {(3, -1), (2, 1)}
    # 恰好三小步，且最后一小步就是落点
    for move in moves:
        assert len(move.path) == 3
        assert move.path[-1] == move.dest


def test_ant_slides_any_distance_along_the_edge(game: HiveGame):
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    targets = move_targets(game, state, (0, 0))
    # 能一路滑到蜂巢另一头的 (4,0)（离起点 4 格），但绝不能落在有棋的格子上
    assert (4, 0) in targets
    assert not targets & {(1, 0), (2, 0), (3, 0)}
    assert len(targets) == 9


def test_ant_reaches_everywhere_the_spider_can(game: HiveGame):
    """同一局面下，蜘蛛的三格落点必然是兵蚁落点的子集。"""
    spider = move_targets(game, make_state(_swap_mover(LINE, "spider"), current=0), (0, 0))
    ant = move_targets(game, make_state(_swap_mover(LINE, "ant"), current=0), (0, 0))
    assert spider < ant


# --------------------------------------------------------------------------- #
# 停一手
# --------------------------------------------------------------------------- #


def test_legal_moves_returns_a_pass_rather_than_an_empty_list(game: HiveGame):
    """无处放子又无棋可动时必须**显式**给一个 PassMove。

    空表会让 MCTS 的 rollout 循环一路索取到抛 ``RuntimeError``（AI 线程吞掉
    异常，表现成"AI 突然不下棋"），minimax 也会把它当成"局面价值 0"。
    """
    # 己方唯一的棋（蜂后）被对方甲虫压住 —— 既没有贴己方的落点，也没有可动的棋
    state = make_state(
        {(0, 0): [P(0, "queen"), P(1, "beetle")], (1, 0): [P(1, "ant")]},
        current=0,
    )
    moves = game.legal_moves(state)
    assert len(moves) == 1
    assert isinstance(moves[0], PassMove)
    assert game.is_legal(state, PassMove(0))


def test_pass_is_illegal_when_there_is_a_real_move(game: HiveGame):
    state = game.initial_state()
    assert not game.is_legal(state, PassMove(0))


def test_two_passes_in_a_row_end_the_game_as_a_draw(game: HiveGame):
    stuck = make_state(
        {(0, 0): [P(0, "queen"), P(1, "beetle")], (1, 0): [P(1, "ant")]},
        current=0,
    )
    one = game.apply(stuck, PassMove(0))
    assert one.passes == 1
    assert not one.is_terminal()
    two = game.apply(one, PassMove(1))
    assert two.is_terminal()
    assert two.drawn
    assert two.winner() is None


def test_a_pass_does_not_touch_the_board(game: HiveGame):
    state = game.initial_state()
    after = game.apply(state, PassMove(0))
    assert after.stacks == state.stacks
    assert after.current_player == 1


# --------------------------------------------------------------------------- #
# 胜负
# --------------------------------------------------------------------------- #


def _five_of_six() -> dict:
    """蜂后 (0,0) 的六个邻格里填掉五个，只留 (0,1)。"""
    board = {(0, 0): [P(0, "queen")]}
    for n in neighbors((0, 0)):
        if n != (0, 1):
            board[n] = [P(1, "ant")]
    return board


def _almost_surrounded() -> dict:
    """同 :func:`_five_of_six`，但补刀的那枚棋停在 **(1,1)** 上。

    (1,1) 是"不贴着蜂后"的格子 —— 只有从这种格子挪进 (0,1) 才真的会让包围数
    +1；从 (1,0) 挪过去只是换了个位置，包围数纹丝不动。补刀的棋用**蜂后**，
    这样对方也有蜂后（没蜂后就不能移动任何棋子），不必再摆一枚无关的棋。
    """
    board = _five_of_six()
    board[(1, 1)] = [P(1, "queen")]
    return board


def test_surrounding_the_enemy_queen_wins(game: HiveGame):
    state = make_state(_almost_surrounded(), current=1)
    winning = MoveMove(1, (1, 1), (0, 1))
    assert game.is_legal(state, winning)
    after = game.apply(state, winning)
    assert after.is_terminal()
    assert after.winner() == 1
    assert after.winner_player == 1


def test_a_beetle_on_the_queen_head_is_not_a_surround(game: HiveGame):
    """判据只看蜂后**所在格**的六个邻格 —— 压在她头上不算。"""
    board = _five_of_six()
    board[(0, 0)] = [P(0, "queen"), P(1, "beetle")]
    state = make_state(board, current=1)
    after = game.apply(state, PassMove(1))  # 停一手不改盘面，只为触发判定
    assert after.winner() is None
    assert not after.is_terminal()

    # 补上最后一面 → 压头的甲虫不影响，照样判负
    full = make_state({**board, (0, 1): [P(1, "ant")]}, current=1)
    assert game.apply(full, PassMove(1)).winner() == 1


def test_your_own_pieces_count_when_surrounding(game: HiveGame):
    """占位棋**不分敌我** —— 自己贴上去也算。"""
    board = _five_of_six()
    board[(0, 1)] = [P(0, "ant")]  # 最后一面是**自己**补上的
    # 停一手不改盘面 —— 只是借 apply 触发一次胜负判定
    assert game.apply(make_state(board, current=0), PassMove(0)).winner() == 1


def test_both_queens_surrounded_at_once_is_a_draw(game: HiveGame):
    board = {(0, 0): [P(0, "queen")], (2, 0): [P(1, "queen")]}
    for n in neighbors((0, 0)):
        board[n] = [P(1, "ant")]
    for n in neighbors((2, 0)):
        board.setdefault(n, [P(0, "ant")])
    state = make_state(board, current=0)
    after = game.apply(state, PassMove(0))
    assert after.drawn
    assert after.winner() is None


# --------------------------------------------------------------------------- #
# 着法契约
# --------------------------------------------------------------------------- #


def test_moves_are_hashable_and_comparable(game: HiveGame):
    """MCTS 用 ``dict[Move, _Node]`` 存子节点 —— Move 必须可哈希可比较。"""
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    moves = game.legal_moves(state)
    assert len(set(moves)) == len(moves)


def test_animation_payload_does_not_participate_in_equality(game: HiveGame):
    """视图构造的 Move 必须和 legal_moves 产出的判等，否则 is_legal 会判非法。"""
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    generated = next(m for m in game.legal_moves(state) if isinstance(m, MoveMove))
    plain = MoveMove(generated.player, generated.src, generated.dest)
    assert plain == generated
    assert hash(plain) == hash(generated)
    # 但身份字段不同就必须是另一手
    place = PlaceMove(0, "ant", (0, 0))
    assert place != plain


def test_destinations_are_targets_not_sources(game: HiveGame):
    """视图拿到的是**走完之后**的局面，按源格比对等于一个都对不上。"""
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    move = next(m for m in game.legal_moves(state) if isinstance(m, MoveMove))
    assert move.destinations() == (move.dest,)
    assert move.src not in move.destinations()


def test_is_legal_rejects_foreign_and_unknown_moves(game: HiveGame):
    state = game.initial_state()
    assert not game.is_legal(state, PlaceMove(1, "ant", (0, 0)))
    assert not game.is_legal(state, PassMove(0))


def test_terminal_states_have_no_moves(game: HiveGame):
    state = make_state({(0, 0): [P(0, "queen")]}, winner_player=0)
    assert game.legal_moves(state) == []


# --------------------------------------------------------------------------- #
# 搜索裁剪
# --------------------------------------------------------------------------- #


def test_max_branch_still_returns_legal_moves(game: HiveGame):
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    full = game.legal_moves(state)
    cut = game.legal_moves(state, SearchOptions(max_branch=4, order=True))
    assert len(cut) == 4
    assert set(cut) <= set(full)
    assert all(game.is_legal(state, m) for m in cut)


def test_truncation_is_implicitly_ordered(game: HiveGame):
    """MCTS 传 ``order=False``：不开 order 又开 max_branch 时必须自己排序，
    否则被裁掉的是"生成顺序里靠后的一整类"。"""
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    moves = game.legal_moves(state, SearchOptions(max_branch=4, order=False))
    assert len(moves) == 4
    # 生成顺序是"先放置后移动"，不排序就会把移动整类砍光
    assert any(isinstance(m, (MoveMove, PillbugMove)) for m in moves)


def test_wall_and_special_flags_are_ignored(game: HiveGame):
    """``include_walls`` / ``include_special`` 是步步为营的语义，昆虫棋必须忽略。"""
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    reference = game.legal_moves(state, SearchOptions(max_branch=0, order=False))
    for options in (
        SearchOptions(max_branch=0, order=False, include_walls=False),
        SearchOptions(max_branch=0, order=False, include_special=False),
    ):
        assert len(game.legal_moves(state, options)) == len(reference)


def test_the_mating_move_survives_a_tight_branch_cap(game: HiveGame):
    """一步围死敌后的着法必须排在最前 —— 否则 max_branch 会把它裁掉。"""
    state = make_state(_almost_surrounded(), current=1)
    moves = game.legal_moves(state, SearchOptions(max_branch=3, order=True))
    assert moves[0] == MoveMove(1, (1, 1), (0, 1))


# --------------------------------------------------------------------------- #
# 评估与模拟
# --------------------------------------------------------------------------- #


def test_evaluation_is_antisymmetric(game: HiveGame):
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    for player in (0, 1):
        assert game.evaluate(state, player) == -game.evaluate(state, 1 - player)


def test_evaluation_stays_bounded(game: HiveGame):
    state = make_state(_five_of_six(), current=1)
    assert abs(game.evaluate(state, 0, DEFAULT_WEIGHTS)) < 450


def test_rollout_move_is_always_legal(game: HiveGame):
    rng = random.Random(7)
    state = make_state(_swap_mover(LINE, "ant"), current=0)
    for _ in range(30):
        assert game.is_legal(state, game.rollout_move(state, rng))
