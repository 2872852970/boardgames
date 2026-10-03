"""静态评估：**反对称性**是硬契约。

``evaluate(s, 0) == -evaluate(s, 1)`` 一旦破了，minimax 会在双方都不占便宜的局面里
乱选，而且极难从棋力表现反推回来 —— 所以这里逐步断言，而不是抽查几个局面。
"""

from __future__ import annotations

import random

import pytest
from aba_helpers import make_state

from boardgames.games.abalone import heuristic as heu
from boardgames.games.abalone.heuristic import DEFAULT_WEIGHTS, evaluate
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import initial_state


def test_default_weights_are_all_positive():
    assert set(DEFAULT_WEIGHTS) == {
        "w_abalone_out",
        "w_abalone_center",
        "w_abalone_cohere",
        "w_abalone_danger",
    }
    assert all(v > 0 for v in DEFAULT_WEIGHTS.values())


def test_evaluation_is_antisymmetric_through_a_whole_game():
    """一整局（随机 rollout）每一步都必须满足反对称。"""
    game = AbaloneGame("belgian_daisy")
    state = game.initial_state()
    rng = random.Random(20261003)
    checked = 0
    for _ in range(400):
        assert evaluate(state, 0) == -evaluate(state, 1), f"ply={state.ply} 破坏反对称"
        checked += 1
        if state.is_terminal():
            break
        state = game.apply(state, game.rollout_move(state, rng))
    assert checked > 20


@pytest.mark.parametrize("key", sorted(DEFAULT_WEIGHTS))
def test_each_feature_alone_is_antisymmetric(key):
    """只开一个权重时也要反对称 —— 逐项排查是哪一项写错了符号。"""
    weights = {k: (1.0 if k == key else 0.0) for k in DEFAULT_WEIGHTS}
    game = AbaloneGame("german_daisy")
    state = game.initial_state()
    rng = random.Random(7)
    for _ in range(60):
        assert evaluate(state, 0, weights) == -evaluate(state, 1, weights), key
        if state.is_terminal():
            break
        state = game.apply(state, game.rollout_move(state, rng))


def test_terminal_positions_score_plus_or_minus_mate(game):
    """终局必须给 ±MATE —— 前提是 **winner_player 已经被 apply 设上**。

    手搭局面时只写 ``out=(6, 0)`` 是不够的：``winner_player`` 不会自动推导出来，
    ``evaluate`` 只会把它当成一个"领先 6 枚"的普通局面（实测 1344 分）。
    所以这里走一次真实的挤出，让引擎自己盖章。
    """
    state = make_state({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0), current=0)
    over = game.apply(
        state, next(m for m in game.legal_moves(state) if m.direction == 0 and len(m.cells) == 2)
    )
    assert over.is_terminal() and over.winner() == 0
    assert evaluate(over, 0) == heu.MATE
    assert evaluate(over, 1) == -heu.MATE
    assert evaluate(over, 0) == -evaluate(over, 1)


def test_ejecting_lead_is_dominant():
    """多挤出一枚的领先必须体现在分数上，且方向正确。"""
    base = make_state({(0, 0): 1, (-1, 0): 1, (1, 0): 2}, current=0)
    ahead = make_state({(0, 0): 1, (-1, 0): 1, (1, 0): 2}, out=(1, 0), current=0)
    assert evaluate(ahead, 0) > evaluate(base, 0)
    assert evaluate(ahead, 1) < evaluate(base, 1)


def test_center_control_prefers_the_middle():
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0.0) | {"w_abalone_center": 1.0}
    middle = make_state({(0, 0): 1, (-1, 0): 1}, current=0)
    edge = make_state({(-4, 0): 1, (-3, 0): 1}, current=0)
    assert evaluate(middle, 0, weights) > evaluate(edge, 0, weights)


def test_cohesion_prefers_a_tight_group():
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0.0) | {"w_abalone_cohere": 1.0}
    tight = make_state({(0, 0): 1, (1, 0): 1, (-1, 0): 1}, current=0)
    loose = make_state({(0, 0): 1, (2, -2): 1, (-3, 3): 1}, current=0)
    assert heu.cohesion(tight, 1) == 2
    assert heu.cohesion(loose, 1) == 0
    assert evaluate(tight, 0, weights) > evaluate(loose, 0, weights)


def test_edge_danger_penalises_hugging_the_rim():
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0.0) | {"w_abalone_danger": 1.0}
    middle = make_state({(0, 0): 1}, current=0)
    edge = make_state({(4, 0): 1}, current=0)
    assert evaluate(middle, 0, weights) > evaluate(edge, 0, weights)


def test_unknown_weight_keys_are_ignored():
    """别的棋类的权重（如墙棋的 w_path）传进来必须毫无影响。"""
    state = initial_state()
    base = evaluate(state, 0)
    assert evaluate(state, 0, {"w_path": 999.0, "w_tempo": 5.0}) == base
    assert evaluate(state, 0, {"w_abalone_out": "not a number"}) == base


def test_weights_are_actually_applied():
    """权重确实乘到了分数上：全关 = 0，单开一项 = 那一项的值。"""
    state = make_state({(0, 0): 1}, out=(1, 0), current=0)
    off = dict.fromkeys(DEFAULT_WEIGHTS, 0.0)
    assert evaluate(state, 0, off) == 0.0, "所有权重归零时必须一分不给"
    assert evaluate(state, 0, off | {"w_abalone_out": 100.0}) == 100.0
    assert evaluate(state, 0, off | {"w_abalone_out": 1000.0}) == 1000.0


def test_score_stays_inside_the_tanh_useful_range():
    """非终局分数要留在 MCTS ``tanh(score / 600)`` 还能分辨领先幅度的区间里。

    实测：一枚之差 ≈ 240，落后 3 枚 ≈ 725。``tanh(725/600) = 0.84`` 仍有梯度，
    但一旦超过 ~1800 就会被彻底拍平成 ±1，rollout 回报再区分不出"赢多少" ——
    所以阈值定在 1500，并且要求它离 MATE 还有两个数量级。
    """
    game = AbaloneGame()
    state = game.initial_state()
    rng = random.Random(11)
    for _ in range(150):
        if state.is_terminal():
            break
        score = abs(evaluate(state, state.current))
        assert score < 1500.0, f"ply={state.ply} score={score} 已饱和"
        assert score < heu.MATE / 100
        state = game.apply(state, game.rollout_move(state, rng))


def test_initial_position_is_balanced():
    """标准开局双方完全对称，先手视角的分数应当很小。"""
    assert abs(evaluate(initial_state("standard"), 0)) < 30.0
