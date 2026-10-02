"""AI 引擎注册表。

侧栏通过 :func:`all_engines` 列出可选算法，通过 :func:`get_engine` 按 key 取用。
新增算法只需实现 :class:`AIEngine` 并在这里注册一行。
"""

from __future__ import annotations

from boardgames.ai.engine import (
    AIEngine,
    AIEngineParams,
    SearchContext,
    SearchResult,
    SearchStats,
)
from boardgames.ai.mcts import MCTSEngine
from boardgames.ai.minimax import MinimaxEngine
from boardgames.ai.random_ai import RandomEngine
from boardgames.ai.worker import AIWorker

_ENGINES: dict[str, AIEngine] = {}
_ORDER: list[str] = []


def register_engine(engine: AIEngine) -> None:
    if engine.key in _ENGINES:
        raise ValueError(f"引擎 key 重复注册: {engine.key!r}")
    _ENGINES[engine.key] = engine
    _ORDER.append(engine.key)


def get_engine(key: str) -> AIEngine:
    try:
        return _ENGINES[key]
    except KeyError:
        raise KeyError(f"未注册的 AI 引擎: {key!r}（可选: {sorted(_ENGINES)}）") from None


def all_engines() -> list[AIEngine]:
    return [_ENGINES[k] for k in _ORDER]


def engine_keys() -> list[str]:
    return list(_ORDER)


register_engine(MinimaxEngine())
register_engine(MCTSEngine())
register_engine(RandomEngine())

__all__ = [
    "AIEngine",
    "AIEngineParams",
    "AIWorker",
    "MCTSEngine",
    "MinimaxEngine",
    "RandomEngine",
    "SearchContext",
    "SearchResult",
    "SearchStats",
    "all_engines",
    "engine_keys",
    "get_engine",
    "register_engine",
]
