"""评估函数：对称性、威胁检测、量级。"""

from __future__ import annotations

from boardgames.games.connect4.heuristic import center_weights, winning_columns
from conftest import make_at


def test_evaluate_is_zero_on_empty_board(game):
    state = game.initial_state()
    assert game.evaluate(state, 0) == 0.0
    assert game.evaluate(state, 1) == 0.0


def test_evaluate_is_antisymmetric(game):
    """``evaluate(s, 0) == -evaluate(s, 1)`` —— minimax 靠这条挑边。"""
    state = make_at(7, 6, {
        (0, 0): 1, (1, 0): 1, (2, 0): 1,
        (5, 0): 2, (6, 0): 2, (4, 0): 2, (3, 1): 2,
    })
    assert game.evaluate(state, 0) == -game.evaluate(state, 1)


def test_evaluate_favours_material(game):
    a = make_at(7, 6, {(0, 0): 1, (1, 0): 1, (2, 0): 1, (3, 0): 1})
    b = make_at(7, 6, {(0, 0): 1, (1, 0): 1})
    assert game.evaluate(a, 0) > game.evaluate(b, 0)


def test_evaluate_favours_center(game):
    """同样一枚子放中间比放边角好。"""
    center = make_at(7, 6, {(3, 0): 1})
    edge = make_at(7, 6, {(0, 0): 1})
    assert game.evaluate(center, 0) > game.evaluate(edge, 0)


def test_evaluate_favours_threat(game):
    """我方有三连（下一手能赢）应当明显加分。"""
    threat = make_at(7, 6, {(0, 0): 1, (1, 0): 1, (2, 0): 1})
    calm = make_at(7, 6, {(0, 0): 1, (6, 0): 1})
    assert game.evaluate(threat, 0) > game.evaluate(calm, 0)


def test_evaluate_penalises_opponent_threat(game):
    """对手有活三要扣分（甚至比我有活三更该担心）。"""
    mine = make_at(7, 6, {(0, 0): 1, (1, 0): 1, (2, 0): 1})
    theirs = make_at(7, 6, {(4, 0): 2, (5, 0): 2, (6, 0): 2})
    assert game.evaluate(theirs, 0) < 0
    assert game.evaluate(theirs, 0) < game.evaluate(mine, 0)


def test_winning_columns_finds_immediate_win(game):
    state = make_at(7, 6, {(0, 0): 1, (1, 0): 1, (2, 0): 1})
    # 投第 3 列即成四
    assert winning_columns(state, 0) == 1
    # 换成对手视角：对手没有威胁
    assert winning_columns(state, 1) == 0


def test_winning_columns_ignores_blocked_columns(game):
    """已满的列不能算威胁。"""
    state = make_at(7, 2, {(0, r): 1 for r in range(2)})
    assert 0 not in game.open_columns(state)


def test_center_weights_symmetric():
    weights = center_weights(7)
    assert len(weights) == 7
    assert weights[3] == max(weights)
    assert weights[0] == weights[6]
    assert weights[1] == weights[5]
    assert weights[2] == weights[4]
    assert weights[0] < weights[3]


def test_center_weights_even_board():
    weights = center_weights(8)
    assert len(weights) == 8
    assert max(weights) in (weights[3], weights[4])
    assert weights == tuple(reversed(weights))


def test_center_weights_single_column():
    assert center_weights(1) == (1.0,)


def test_weights_from_settings_are_applied(game):
    """侧栏把权重传进来后应当生效。"""
    state = make_at(7, 6, {(0, 0): 1, (1, 0): 1, (2, 0): 1})
    default = game.evaluate(state, 0)
    boosted = game.evaluate(state, 0, {"w_threat": 600.0})
    assert boosted > default


def test_evaluate_magnitude_is_reasonable(game):
    """中局评估分的量级要能被 ``mcts.ROLLOUT_VALUE_SCALE`` 压进 tanh 的有效区间。

    分太小会让 rollout 回报恒等于 0（MCTS 退化成只看终局）。
    """
    import random

    from boardgames.games.connect4.state import initial_state

    state = initial_state(7, 6, 0)
    rng = random.Random(4)
    scores = []
    for _ in range(30):
        for _ in range(12):
            if state.is_terminal():
                break
            state = game.apply(state, game.rollout_move(state, rng, None, None))
        if not state.is_terminal():
            scores.append(abs(game.evaluate(state, 0)))
    assert scores, "应当采到一些中局样本"
    median = sorted(scores)[len(scores) // 2]
    # 太小（<5）说明 tanh(score/600)≈0，rollout 失去区分度
    assert median > 5.0, f"评估分中位数 {median:.1f} 过小，MCTS rollout 会失去区分度"
