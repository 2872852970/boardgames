"""随机走子引擎（基线 / 对照，也用于测试）。"""

from __future__ import annotations

import random
import time

from boardgames.ai.engine import (
    AIEngine,
    AIEngineParams,
    SearchContext,
    SearchResult,
    SearchStats,
)
from boardgames.core.game import Game
from boardgames.core.move import Move
from boardgames.core.state import State


class RandomEngine(AIEngine):
    key = "random"
    display_name = "随机走子"
    param_groups = ()

    def search(
        self,
        game: Game,
        state: State,
        player: int,
        params: AIEngineParams,
        ctx: SearchContext,
    ) -> SearchResult:
        t0 = time.perf_counter()
        rng = random.Random(params.seed)
        moves: list[Move] = game.legal_moves(state)
        stats = SearchStats(engine=self.key, engine_name=self.display_name)
        stats.elapsed_ms = (time.perf_counter() - t0) * 1000
        stats.depth_reached = 1
        if not moves:
            return SearchResult(None, stats)
        return SearchResult(rng.choice(moves), stats)
