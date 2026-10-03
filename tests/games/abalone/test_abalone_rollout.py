"""MCTS 的 rollout 策略。

纯随机在大力士棋上几乎打不出结果（走 300 手双方各只挤出 1~2 子），
所以策略**必须**偏向推挤 —— 这几条测试锁的就是这个偏向。
"""

from __future__ import annotations

import random

import pytest
from aba_helpers import make_state

from boardgames.games.abalone.state import initial_state


@pytest.mark.parametrize("setup", ["standard", "belgian_daisy", "german_daisy"])
def test_rollout_always_returns_a_legal_move(game, setup):
    state = initial_state(setup)
    rng = random.Random(3)
    for _ in range(200):
        if state.is_terminal():
            break
        move = game.rollout_move(state, rng)
        assert game.is_legal(state, move), f"{move.describe()} 不合法"
        state = game.apply(state, move)


def test_rollout_prefers_ejections(game):
    """有能挤出盘外的着法时，绝大多数采样都该选它。"""
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2, (-3, 2): 1, (0, -4): 2}, current=0)
    moves = game.legal_moves(state)
    assert any(m.ejected is not None for m in moves), "这个局面本身要存在「挤出」着法"
    rng = random.Random(5)
    hits = sum(
        1 for _ in range(200) if game.rollout_move(state, rng).ejected is not None
    )
    assert hits >= 160, f"只有 {hits}/200 次采样选中了挤出着法"


def test_rollout_terminates_a_game(game):
    """双方都用 rollout 策略对弈，1000 手内必然分出胜负（挤出 6 子）。"""
    for seed in (1, 2, 3):
        state = initial_state("belgian_daisy")
        rng = random.Random(seed)
        for _ in range(1000):
            if state.is_terminal():
                break
            state = game.apply(state, game.rollout_move(state, rng))
        assert state.is_terminal(), f"seed={seed} 1000 手还没分胜负，out={state.out}"
        assert state.out[state.winner()] >= 6


def test_rollout_is_seed_reproducible(game):
    state = initial_state()
    a = [game.rollout_move(state, random.Random(42)).describe() for _ in range(1)]
    b = [game.rollout_move(state, random.Random(42)).describe() for _ in range(1)]
    assert a == b


def test_rollout_raises_on_terminal(game):
    state = make_state({(0, 0): 1}, out=(6, 0), current=1)
    with pytest.raises(RuntimeError):
        game.rollout_move(state, random.Random(0))


def test_fully_played_game_keeps_move_counts_sane(game):
    """整局过程中着法数始终在合理区间（不是 0，也不会爆炸）。"""
    state = initial_state("german_daisy")
    rng = random.Random(9)
    while not state.is_terminal():
        count = len(game.legal_moves(state))
        assert count > 0, "任何非终局局面都必须有合法着法"
        assert count < 200
        state = game.apply(state, game.rollout_move(state, rng))
