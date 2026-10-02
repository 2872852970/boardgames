"""游戏注册表 —— 插件式接入点。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from boardgames.core.game import Game


@dataclass
class GameRegistry:
    """`key -> (Game, view_factory)` 的注册表。

    新增棋类时只需注册三样东西：规则引擎、棋盘视图工厂、展示名。
    """

    _games: dict[str, Game] = field(default_factory=dict)
    _views: dict[str, Callable[..., object]] = field(default_factory=dict)

    def register(self, game: Game, view_factory: Callable[..., object] | None = None) -> None:
        if game.key in self._games:
            raise ValueError(f"游戏 key 重复注册: {game.key!r}")
        self._games[game.key] = game
        if view_factory is not None:
            self._views[game.key] = view_factory

    def get(self, key: str) -> Game:
        try:
            return self._games[key]
        except KeyError:
            raise KeyError(f"未注册的游戏: {key!r}（已注册: {sorted(self._games)}）") from None

    def view_factory(self, key: str) -> Callable[..., object] | None:
        return self._views.get(key)

    def register_view(self, key: str, factory: Callable[..., object]) -> None:
        """单独注册棋盘视图（让 core 层不必 import 任何 UI 代码）。"""
        if key not in self._games:
            raise KeyError(f"请先注册游戏再注册视图: {key!r}")
        self._views[key] = factory

    def keys(self) -> list[str]:
        return list(self._games)

    def all_games(self) -> list[Game]:
        return list(self._games.values())

    def __contains__(self, key: object) -> bool:
        return key in self._games

    def __len__(self) -> int:
        return len(self._games)


def build_default_registry() -> GameRegistry:
    """组装内置游戏。新增棋类在这里挂一行即可。"""
    from boardgames.games.quoridor.rules import QuoridorGame

    registry = GameRegistry()
    registry.register(QuoridorGame())
    return registry
