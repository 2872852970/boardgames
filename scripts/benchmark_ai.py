"""AI 性能基准：用来给搜索参数定默认值。

用法：``uv run python scripts/benchmark_ai.py``
"""

from __future__ import annotations

import statistics
import time

from boardgames.ai import AIEngineParams, SearchContext, get_engine
from boardgames.games.quoridor import geometry as geo
from boardgames.games.quoridor.rules import QuoridorGame


def bench(label: str, fn, repeat: int = 3) -> float:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    median = statistics.median(times)
    print(f"{label:<40} {median:8.2f} ms")
    return median


def main() -> None:
    game = QuoridorGame()
    state = game.initial_state()

    print("=== 基础代价 ===")
    bench("pawn_moves_for", lambda: game.pawn_moves_for(state, 0), 20)
    bench("candidate_walls(limit=12)", lambda: game.candidate_walls(state, 0, 12), 10)
    bench("candidate_walls(limit=8)", lambda: game.candidate_walls(state, 0, 8), 10)
    bench("geometric_wall_candidates", lambda: game.geometric_wall_candidates(state, 0), 10)
    bench("all_legal_walls (128)", lambda: game.all_legal_walls(state, 0), 5)
    bench(
        "shortest_path x2",
        lambda: (
            geo.shortest_path(state.size, state.h_mask, state.v_mask, state.pawns[0], 0),
            geo.shortest_path(state.size, state.h_mask, state.v_mask, state.pawns[1], 8),
        ),
        50,
    )
    print()

    print("=== 一个 rollout 的代价 ===")
    import random as _random

    rng = _random.Random(1)

    def one_rollout() -> None:
        s = state
        for _ in range(48):
            if s.is_terminal():
                break
            s = game.apply(s, game.rollout_move(s, rng, None, None))

    bench("rollout (cap=48, p_wall=0.12)", one_rollout, 20)
    bench("rollout (cap=24)", lambda: [one_rollout() for _ in range(1)], 10)
    print()

    print("=== Minimax ===")
    for depth in (1, 2, 3, 4):
        engine = get_engine("minimax")
        params = AIEngineParams(depth=depth, wall_depth=2, max_branch=12, time_limit_ms=10_000)
        result = engine.search(game, state, 0, params, SearchContext(10_000))
        move = result.move.describe() if result.move else None
        print(
            f"  depth={depth}  {result.stats.elapsed_ms:9.1f} ms  "
            f"nodes={result.stats.nodes:<9} {move}"
        )
    print()

    print("=== Minimax wall_depth 的影响（depth=3, max_branch=12）===")
    for wall_depth in (1, 2, 3):
        engine = get_engine("minimax")
        params = AIEngineParams(depth=3, wall_depth=wall_depth, max_branch=12, time_limit_ms=10_000)
        result = engine.search(game, state, 0, params, SearchContext(10_000))
        move = result.move.describe() if result.move else None
        print(
            f"  wall_depth={wall_depth}  {result.stats.elapsed_ms:9.1f} ms  "
            f"nodes={result.stats.nodes:<9} {move}"
        )
    print()

    print("=== MCTS ===")
    for iterations in (200, 500, 1000):
        engine = get_engine("mcts")
        params = AIEngineParams(iterations=iterations, max_branch=10, time_limit_ms=60_000, seed=1)
        result = engine.search(game, state, 0, params, SearchContext(60_000))
        move = result.move.describe() if result.move else None
        win = result.stats.win_rate if result.stats.win_rate is not None else 0.0
        print(
            f"  iters={iterations:<6} {result.stats.elapsed_ms:9.1f} ms  实际={result.stats.iterations:<6} "
            f"胜率={win:.2f}  {move}"
        )
    print()

    print("=== MCTS 时限 1200ms ===")
    engine = get_engine("mcts")
    params = AIEngineParams(iterations=10**9, max_branch=10, time_limit_ms=1200, seed=1)
    result = engine.search(game, state, 0, params, SearchContext(1200))
    nps = result.stats.iterations / max(result.stats.elapsed_ms / 1000, 1e-6)
    print(f"  用时 {result.stats.elapsed_ms:.1f} ms  迭代 {result.stats.iterations}  nps={nps:.0f}")
    print()

    print("=== 对局强度 ===")
    wins = play_match(game, "minimax", "random", AIEngineParams(depth=3, wall_depth=2, time_limit_ms=3000), 6)
    print(f"  Minimax(d3) vs 随机: {wins}/6")
    wins = play_match(game, "mcts", "random", AIEngineParams(iterations=400, time_limit_ms=3000), 6)
    print(f"  MCTS(400)  vs 随机: {wins}/6")
    wins = play_match(game, "minimax", "mcts", AIEngineParams(depth=3, wall_depth=2, time_limit_ms=3000), 4,
                      params_b=AIEngineParams(iterations=400, time_limit_ms=3000))
    print(f"  Minimax(d3) vs MCTS(400): {wins}/4")


def play_match(
    game: QuoridorGame,
    key_a: str,
    key_b: str,
    params_a: AIEngineParams,
    games: int = 4,
    params_b: AIEngineParams | None = None,
) -> int:
    """player 0 用引擎 A，player 1 用引擎 B。返回 A 的胜局数。"""
    engine_a = get_engine(key_a)
    engine_b = get_engine(key_b)
    params_b = params_b or params_a
    wins_a = 0
    for g in range(games):
        state = game.initial_state(first_player=0)
        plies = 0
        while not state.is_terminal() and plies < 300:
            if state.current == 0:
                engine, params = engine_a, params_a
            else:
                engine, params = engine_b, params_b
            p = params.copy(seed=g * 977 + plies)
            result = engine.search(game, state, state.current, p, SearchContext(p.time_limit_ms))
            if result.move is None:
                break
            assert game.is_legal(state, result.move), f"非法着法: {result.move}"
            state = game.apply(state, result.move)
            plies += 1
        if state.winner() == 0:
            wins_a += 1
        print(f"    game {g}: winner={state.winner()} plies={plies}")
    return wins_a


if __name__ == "__main__":
    main()
