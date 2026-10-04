"""播棋规则测试。

播种方向（标准 Kalah，逆时针）：
* 玩家 0：``0,1,...,5, store0, 11,10,...,6``
* 玩家 1：``11,10,...,6, store1, 0,1,...,5``
"""

from __future__ import annotations

import pytest

from boardgames.games.mancala.move import SowMove
from boardgames.games.mancala.rules import MancalaGame
from boardgames.games.mancala.state import MancalaState, initial_state, sow_path


def make_state(
    pits: list[int],
    stores: tuple[int, int] = (0, 0),
    *,
    current: int = 0,
    pits_per_side: int = 6,
) -> MancalaState:
    """按坑序造局面（前 6 个玩家 0，后 6 个玩家 1）。"""
    assert len(pits) == 2 * pits_per_side
    return MancalaState(
        pits_per_side=pits_per_side,
        pits=tuple(pits),
        stores=stores,
        current=current,
        ply=0,
    )


@pytest.fixture
def game() -> MancalaGame:
    return MancalaGame()


# --------------------------------------------------------------------------- #
# sow_path：播种路径
# --------------------------------------------------------------------------- #


def test_sow_path_player0_full_cycle() -> None:
    """玩家 0 播 13 粒（一整圈 + 1）：经过自己仓库一次，跳过对手仓库。"""
    path = sow_path(6, 0, 0, 13)
    stores = [idx for idx, is_store in path if is_store]
    assert stores == [0]                # 只进自己仓库，绝不进对手仓库
    assert path[5] == (0, True)         # 第 6 步落自己仓库（坑1..5 之后）
    assert path[6] == (11, False)       # 之后进入对手坑（从 11 递减）


def test_sow_path_player1_direction() -> None:
    """玩家 1 沿逆时针：从坑 11 出发第一步是坑 10。"""
    path = sow_path(6, 11, 1, 2)
    assert path[0] == (10, False)
    assert path[1] == (9, False)


def test_sow_path_player1_hits_own_store() -> None:
    """玩家 1 从坑 6（自己最左）播 1 粒正好落己方仓库。"""
    path = sow_path(6, 6, 1, 1)
    assert path == [(1, True)]


# --------------------------------------------------------------------------- #
# 基本着法
# --------------------------------------------------------------------------- #


def test_initial_moves_are_own_nonempty_pits(game: MancalaGame) -> None:
    s = game.initial_state()
    moves = game.legal_moves(s)
    assert sorted(m.pit for m in moves) == [0, 1, 2, 3, 4, 5]


def test_cannot_sow_opponent_pit(game: MancalaGame) -> None:
    s = game.initial_state()
    assert not game.is_legal(s, SowMove(8, 0))    # 对手的坑
    assert not game.is_legal(s, SowMove(0, 1))    # player 字段不对


def test_cannot_sow_empty_pit(game: MancalaGame) -> None:
    s = make_state([0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4])
    assert not game.is_legal(s, SowMove(0, 0))


def test_apply_sows_seeds(game: MancalaGame) -> None:
    """从坑 0（4 粒）播种：坑 0 清空，坑 1~4 各 +1，不涉及仓库/对手坑。"""
    s = game.initial_state()
    nxt = game.apply(s, SowMove(0, 0))
    assert nxt.pits[0] == 0
    assert [nxt.pits[i] for i in (1, 2, 3, 4)] == [5, 5, 5, 5]
    assert nxt.stores == (0, 0)
    assert nxt.current == 1
    # 原状态不可变
    assert s.pits[0] == 4


def test_seed_count_is_conserved(game: MancalaGame) -> None:
    s = game.initial_state()
    nxt = game.apply(s, SowMove(2, 0))
    assert nxt.total_seeds() == s.total_seeds() == 48


# --------------------------------------------------------------------------- #
# 额外回合
# --------------------------------------------------------------------------- #


def test_last_seed_in_store_grants_extra_turn(game: MancalaGame) -> None:
    """坑 2 播 4 粒：落坑 3、4、5、仓库 → 最后一粒进仓库 → 再走一手。"""
    s = make_state([4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4])
    nxt = game.apply(s, SowMove(2, 0))
    assert nxt.stores[0] == 1
    assert nxt.current == 0            # 额外回合
    assert not nxt.is_terminal()


def test_last_seed_not_in_store_switches_turn(game: MancalaGame) -> None:
    s = game.initial_state()
    nxt = game.apply(s, SowMove(0, 0))  # 4 粒落在坑 1~4，不进仓库
    assert nxt.stores[0] == 0
    assert nxt.current == 1


# --------------------------------------------------------------------------- #
# 捕获
# --------------------------------------------------------------------------- #


def test_landing_on_empty_own_pit_captures(game: MancalaGame) -> None:
    """最后一粒落在己方空坑 → 收走这一粒 + 对面坑的全部种子。"""
    # 坑 3 有 1 粒，坑 4 空；对面坑 10（=4+6，同列）有 5 粒。
    s = make_state([0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 5, 0], current=0)
    nxt = game.apply(s, SowMove(3, 0))
    # 从坑 3 播 1 粒 → 落坑 4（空）→ 捕获对面坑 10
    assert nxt.pits[4] == 0            # 这一粒也收进仓库了
    assert nxt.pits[10] == 0           # 对面被收走
    assert nxt.stores[0] == 1 + 5      # 自己这粒 + 对面 5 粒
    assert nxt.current == 1


def test_no_capture_when_landing_on_nonempty_pit(game: MancalaGame) -> None:
    """落在己方**有种子**的坑不触发捕获。"""
    s = make_state([0, 0, 0, 1, 3, 0, 0, 0, 0, 0, 5, 0], current=0)
    nxt = game.apply(s, SowMove(3, 0))
    # 坑 3 播 1 粒落坑 4（已有 3 粒，非空）→ 无捕获，坑 4 变 4
    assert nxt.pits[4] == 4
    assert nxt.pits[10] == 5           # 对面没被动
    assert nxt.stores[0] == 0


def test_no_capture_on_opponent_pit(game: MancalaGame) -> None:
    """最后一粒落在**对手**坑上（即使是空坑）不触发捕获。"""
    # 坑 4 播 4 粒：坑 5、store、坑 11、坑 10（对手坑 10 空）
    s = make_state([4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 0, 4], current=0)
    nxt = game.apply(s, SowMove(4, 0))
    assert nxt.stores[0] == 1
    assert nxt.pits[10] == 1           # 只是 +1，没被收走
    assert nxt.stores[1] == 0


# --------------------------------------------------------------------------- #
# 终局
# --------------------------------------------------------------------------- #


def test_game_ends_when_a_side_empties(game: MancalaGame) -> None:
    """一方小坑全空 → 终局，对手收走剩余。"""
    # 玩家 0 只剩坑 0 有 1 粒；玩家 1 每坑 3 粒。
    # 从坑 0 播 1 粒 → 落坑 1（空）→ 捕获对面坑 7（=1+6）的 3 粒 → 玩家 0 清空。
    s = make_state([1, 0, 0, 0, 0, 0, 3, 3, 3, 3, 3, 3], stores=(10, 10), current=0)
    nxt = game.apply(s, SowMove(0, 0))
    assert nxt.is_terminal()
    assert sum(nxt.pits) == 0
    # 玩家0：10 + 捕获(3+1)；玩家1：10 + 收走剩余 5×3
    assert nxt.stores == (14, 25)
    assert nxt.winner() == 1


def test_draw_returns_terminal_but_no_winner(game: MancalaGame) -> None:
    """仓库打平 → 终局但无胜者。"""
    from dataclasses import replace

    s = make_state([0] * 12, stores=(24, 24))
    final = replace(s, over=True)
    assert final.is_terminal()
    assert final.winner() is None
    assert game.legal_moves(final) == []


def test_terminal_state_has_no_moves(game: MancalaGame) -> None:
    from dataclasses import replace

    s = make_state([0] * 12, stores=(20, 28))
    final = replace(s, over=True, winner_player=1)
    assert final.is_terminal()
    assert game.legal_moves(final) == []


# --------------------------------------------------------------------------- #
# 哈希 / 评估
# --------------------------------------------------------------------------- #


def test_zobrist_same_position_same_hash(game: MancalaGame) -> None:
    a = game.initial_state()
    b = initial_state(6, 4)
    assert a.zobrist_hash() == b.zobrist_hash()
    s = game.initial_state()
    after = game.apply(s, SowMove(0, 0))
    rebuilt = make_state([0, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4], current=1)
    assert after.zobrist_hash() == rebuilt.zobrist_hash()


def test_evaluate_is_antisymmetric(game: MancalaGame) -> None:
    import random

    rng = random.Random(7)
    s = game.initial_state()
    for _ in range(40):
        assert game.evaluate(s, 0) == pytest.approx(-game.evaluate(s, 1))
        if s.is_terminal():
            break
        s = game.apply(s, rng.choice(game.legal_moves(s)))


def test_evaluate_prefers_more_seeds(game: MancalaGame) -> None:
    ahead = make_state([4] * 12, stores=(10, 2))
    behind = make_state([4] * 12, stores=(2, 10))
    assert game.evaluate(ahead, 0) > game.evaluate(behind, 0)


# --------------------------------------------------------------------------- #
# 整局收敛
# --------------------------------------------------------------------------- #


def test_full_game_terminates(game: MancalaGame) -> None:
    """随机 rollout 也要能稳定跑完一局（种子守恒）。"""
    import random

    rng = random.Random(42)
    s = game.initial_state()
    total = s.total_seeds()
    for _ in range(500):
        if s.is_terminal():
            break
        s = game.apply(s, game.rollout_move(s, rng))
    assert s.is_terminal()
    assert s.total_seeds() == total
