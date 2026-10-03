"""rollout 策略：必须单调收敛（不可能振荡），并且抓住即时胜负。"""

from __future__ import annotations

import random

from conftest import make_at


def test_rollout_terminates_within_board_size(game):
    """四子棋每步必然填一格 → 任何合法序列都在 ≤ cols*rows 步内终止。

    这是比墙棋更强的保证：墙棋的棋子能来回走，需要靠距离场强制单调；
    四子棋的棋盘不可逆，振荡在数学上不可能发生。
    """
    for seed in range(30):
        state = game.initial_state()
        rng = random.Random(seed)
        steps = 0
        limit = state.cols * state.rows
        while not state.is_terminal():
            state = game.apply(state, game.rollout_move(state, rng, None, None))
            steps += 1
            assert steps <= limit, f"seed={seed} 走了 {steps} 步，超过 {limit}"
        assert state.is_terminal()


def test_rollout_always_returns_legal_move(game):
    state = game.initial_state()
    rng = random.Random(0)
    for _ in range(20):
        if state.is_terminal():
            break
        move = game.rollout_move(state, rng, None, None)
        assert game.is_legal(state, move)
        state = game.apply(state, move)


def test_rollout_takes_immediate_win(game):
    """我方下一手能赢就必须赢。"""
    state = make_at(7, 6, {(c, 0): 1 for c in (0, 1, 2)}, current=0)
    for seed in range(5):
        move = game.rollout_move(state, random.Random(seed), None, None)
        assert move.col == 3, f"seed={seed} 应当直接赢（第 4 列）"


def test_rollout_blocks_immediate_loss(game):
    """对手下一手能赢时必须堵。"""
    state = make_at(7, 6, {(c, 0): 2 for c in (0, 1, 2)}, current=1)
    for seed in range(5):
        move = game.rollout_move(state, random.Random(seed), None, None)
        assert move.col == 3, f"seed={seed} 应当堵住第 4 列"


def test_rollout_raises_on_terminal_state(game):
    """已分出胜负的局面不该再要着法。"""
    import pytest

    # 2 行小盘，落两子就满；先造出真正的终局
    small = type(game)(cols=3, rows=2)
    state = small.initial_state()
    for _ in range(6):
        if state.is_terminal():
            break
        state = small.apply(state, small.rollout_move(state, random.Random(0), None, None))
    assert state.is_terminal()
    with pytest.raises(RuntimeError):
        small.rollout_move(state, random.Random(0), None, None)


def test_rollout_is_deterministic_given_seed(game):
    """固定种子 → 同样的着法序列（MCTS 的 rollout 必须可复现）。"""
    a = game.initial_state()
    b = game.initial_state()
    ra, rb = random.Random(42), random.Random(42)
    for _ in range(10):
        if a.is_terminal():
            break
        ma = game.rollout_move(a, ra, None, None)
        mb = game.rollout_move(b, rb, None, None)
        assert ma == mb
        a = game.apply(a, ma)
        b = game.apply(b, mb)


def test_rollout_prefers_center_when_no_threat(game):
    """没有即时威胁时应当偏向中心。

    权重是温和的（最高/最低 ≈ 1.6），所以不能断言"中列比所有边列加起来还多"，
    只检验**趋势**：越靠中心被选中的平均次数越多。
    """
    from collections import Counter

    state = make_at(9, 8, {(4, 0): 1, (0, 0): 2}, current=0)
    picks = Counter(
        game.rollout_move(state, random.Random(seed), None, None).col
        for seed in range(900)
    )
    # 两侧对称：把每一对镜像列（1,7）（2,6）（3,5）加总比较
    pairs = [(1, 7), (2, 6), (3, 5)]
    inner = sum(picks[a] + picks[b] for a, b in pairs)      # 离中心 1~3 格
    outer = picks[0] + picks[8]                              # 最外侧两列
    assert inner > outer, f"内侧 6 列共 {inner} 次 vs 最外 2 列共 {outer} 次"
    assert picks[4] == max(picks.values()), "中列应当是最常被选的列"
