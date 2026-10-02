"""后台 AI 线程。

铁律：搜索线程**绝不**触碰 pygame 或任何可变 UI 状态。
主循环每帧调用 :meth:`AIWorker.poll` 取结果即可。
"""

from __future__ import annotations

import threading
import traceback

from boardgames.ai.engine import (
    AIEngine,
    AIEngineParams,
    SearchContext,
    SearchResult,
    SearchStats,
)
from boardgames.core.game import Game
from boardgames.core.state import State


class AIWorker:
    """在后台线程里跑一次搜索，支持取消与过期结果丢弃。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: SearchResult | None = None
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._ctx: SearchContext | None = None
        self._generation = 0

    # ------------------------------------------------------------------ #

    def start(
        self,
        game: Game,
        state: State,
        player: int,
        engine: AIEngine,
        params: AIEngineParams,
    ) -> None:
        self.cancel()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._result = None
            self._error = None
        ctx = SearchContext(params.time_limit_ms)
        self._ctx = ctx
        thread = threading.Thread(
            target=self._run,
            args=(generation, game, state, player, engine, params, ctx),
            name=f"ai-{engine.key}",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def _run(
        self,
        generation: int,
        game: Game,
        state: State,
        player: int,
        engine: AIEngine,
        params: AIEngineParams,
        ctx: SearchContext,
    ) -> None:
        try:
            result = engine.search(game, state, player, params, ctx)
        except Exception:  # noqa: BLE001 - 兜底，避免线程静默死掉
            result = SearchResult(
                None,
                SearchStats(engine=engine.key, engine_name=engine.display_name, cancelled=True),
            )
            with self._lock:
                self._error = traceback.format_exc(limit=3)
        with self._lock:
            if generation == self._generation:
                self._result = result

    # ------------------------------------------------------------------ #

    def poll(self) -> SearchResult | None:
        """取出已完成的结果；没有则返回 ``None``。取走后即清空。"""
        with self._lock:
            result = self._result
            self._result = None
        return result

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def cancel(self) -> None:
        """请求中断当前搜索（悔棋 / 新局 / 切换参数 / 退出时调用）。"""
        ctx = self._ctx
        if ctx is not None:
            ctx.cancel()

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()
