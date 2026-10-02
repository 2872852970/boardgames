"""AI 引擎统一接口。

所有引擎都实现 :class:`AIEngine.search`，因此侧栏可以自由切换算法与参数，
而 UI / controller 完全不需要知道具体是哪种搜索。
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from boardgames.core.game import Game
from boardgames.core.move import Move
from boardgames.core.state import State


@dataclass
class AIEngineParams:
    """可被用户在侧栏实时调整的搜索参数。"""

    #: 思考时间上限（毫秒）
    time_limit_ms: int = 1200
    #: Minimax 迭代加深的最大深度
    depth: int = 4
    #: Minimax 中考虑放墙的最大层数（超过该层只展开走子）
    wall_depth: int = 2
    #: MCTS 迭代次数上限
    iterations: int = 4000
    #: UCT 探索常数
    c_uct: float = 1.414
    #: 每个节点最多考虑多少个"组合爆炸型"着法（如墙位）
    max_branch: int = 12
    #: 是否启用置换表
    tt_enabled: bool = True
    #: rollout 深度上限
    rollout_depth_cap: int = 40
    #: 随机种子（None 表示每次不同）
    seed: int | None = None
    #: 传给游戏评估函数的权重（键名由各游戏定义）
    weights: dict[str, float] = field(default_factory=dict)

    def copy(self, **changes: object) -> AIEngineParams:
        data = {
            "time_limit_ms": self.time_limit_ms,
            "depth": self.depth,
            "wall_depth": self.wall_depth,
            "iterations": self.iterations,
            "c_uct": self.c_uct,
            "max_branch": self.max_branch,
            "tt_enabled": self.tt_enabled,
            "rollout_depth_cap": self.rollout_depth_cap,
            "seed": self.seed,
            "weights": dict(self.weights),
        }
        data.update(changes)
        return AIEngineParams(**data)  # type: ignore[arg-type]


class SearchContext:
    """搜索的截止时间与取消信号。

    搜索线程必须**频繁**调用 :meth:`should_stop`，否则取消会有明显延迟。
    """

    __slots__ = ("deadline", "cancel_event", "_stopped", "_checks")

    def __init__(self, time_limit_ms: int = 1000, cancel_event: threading.Event | None = None):
        self.deadline = time.monotonic() + max(0, time_limit_ms) / 1000.0
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self._stopped = False
        self._checks = 0

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def time_up(self) -> bool:
        return time.monotonic() >= self.deadline

    def should_stop(self) -> bool:
        """廉价的热路径检查：每次都查取消位，每 64 次才读一次时钟。"""
        if self._stopped:
            return True
        if self.cancel_event.is_set():
            self._stopped = True
            return True
        self._checks += 1
        if (self._checks & 63) == 0 and time.monotonic() >= self.deadline:
            self._stopped = True
        return self._stopped


@dataclass
class SearchStats:
    """搜索统计，用于侧栏展示「AI 正在思考…」的细节。"""

    engine: str = ""
    engine_name: str = ""
    elapsed_ms: float = 0.0
    nodes: int = 0
    depth_reached: int = 0
    iterations: int = 0
    score: float | None = None
    win_rate: float | None = None
    pv: list[Move] = field(default_factory=list)
    cancelled: bool = False

    @property
    def nps(self) -> float:
        return self.nodes / (self.elapsed_ms / 1000.0) if self.elapsed_ms > 0 else 0.0

    def summary(self) -> str:
        """给状态栏用的一句话。"""
        parts = [f"{self.engine_name}"]
        if self.iterations:
            parts.append(f"模拟 {self.iterations}")
        if self.depth_reached:
            parts.append(f"深度 {self.depth_reached}")
        if self.nodes:
            parts.append(f"节点 {self.nodes}")
        parts.append(f"{self.elapsed_ms:.0f}ms")
        if self.win_rate is not None:
            parts.append(f"胜率 {self.win_rate * 100:.0f}%")
        elif self.score is not None:
            parts.append(f"评估 {self.score:.0f}")
        return " · ".join(parts)


@dataclass
class SearchResult:
    """搜索结果。``move is None`` 表示搜索被取消（调用方应丢弃结果）。"""

    move: Move | None
    stats: SearchStats = field(default_factory=SearchStats)


class AIEngine(ABC):
    """搜索算法接口。"""

    key: ClassVar[str]
    display_name: ClassVar[str]
    #: 侧栏里是否需要展示 Minimax 参数 / MCTS 参数
    param_groups: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def search(
        self,
        game: Game,
        state: State,
        player: int,
        params: AIEngineParams,
        ctx: SearchContext,
    ) -> SearchResult:
        """为 ``player`` 在 ``state`` 中挑选一步着法。"""

    # ---- 供 UI 复用的小工具 ----

    @staticmethod
    def pick_fallback(game: Game, state: State, rng_seed: int | None = None) -> Move | None:
        import random

        moves = game.legal_moves(state)
        if not moves:
            return None
        return random.Random(rng_seed).choice(moves)
