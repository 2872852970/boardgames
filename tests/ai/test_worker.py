"""AIWorker 后台线程与取消。"""

from __future__ import annotations

import time

from boardgames.ai import AIEngineParams, AIWorker, get_engine


def test_worker_returns_result(game):
    worker = AIWorker()
    worker.start(game, game.initial_state(), 0, get_engine("minimax"), AIEngineParams(depth=2, time_limit_ms=2000))
    deadline = time.monotonic() + 5.0
    result = None
    while result is None and time.monotonic() < deadline:
        result = worker.poll()
        time.sleep(0.01)
    assert result is not None
    assert result.move is not None
    assert game.is_legal(game.initial_state(), result.move)


def test_cancel_stops_search_quickly(game):
    worker = AIWorker()
    params = AIEngineParams(iterations=10**9, depth=14, max_branch=12, time_limit_ms=60_000)
    worker.start(game, game.initial_state(), 0, get_engine("mcts"), params)
    time.sleep(0.15)
    assert worker.is_running()
    t0 = time.perf_counter()
    worker.cancel()
    while worker.is_running() and time.perf_counter() - t0 < 2.0:
        time.sleep(0.01)
    assert not worker.is_running(), "取消后线程未及时退出"


def test_stale_result_is_discarded(game):
    """取消后立刻开新搜索，旧结果不能覆盖新结果。"""
    worker = AIWorker()
    slow = AIEngineParams(iterations=10**9, time_limit_ms=60_000, max_branch=12)
    worker.start(game, game.initial_state(), 0, get_engine("mcts"), slow)
    time.sleep(0.1)
    worker.start(game, game.initial_state(), 0, get_engine("random"), AIEngineParams(seed=7))
    deadline = time.monotonic() + 3.0
    result = None
    while result is None and time.monotonic() < deadline:
        result = worker.poll()
        time.sleep(0.01)
    assert result is not None
    assert result.stats.engine == "random"


def test_worker_survives_engine_errors(game):
    from boardgames.ai import RandomEngine

    class Boom(RandomEngine):
        key = "boom"
        display_name = "会炸的引擎"

        def search(self, *args, **kwargs):
            raise RuntimeError("boom")

    worker = AIWorker()
    worker.start(game, game.initial_state(), 0, Boom(), AIEngineParams())
    deadline = time.monotonic() + 3.0
    result = None
    while result is None and time.monotonic() < deadline:
        result = worker.poll()
        time.sleep(0.01)
    assert result is not None and result.move is None
    assert worker.error is not None
