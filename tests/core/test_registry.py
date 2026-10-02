"""游戏注册表（插件式接入点）。"""

from __future__ import annotations

import pytest

from boardgames.core.registry import GameRegistry, build_default_registry
from boardgames.games.quoridor.rules import QuoridorGame


def test_default_registry_has_quoridor():
    registry = build_default_registry()
    assert "quoridor" in registry
    assert len(registry) >= 1
    game = registry.get("quoridor")
    assert game.key == "quoridor"
    assert game.display_name == "步步为营"
    assert game.player_count() == 2


def test_register_and_lookup():
    registry = GameRegistry()
    game = QuoridorGame()
    registry.register(game, view_factory=lambda theme: "view")
    assert registry.keys() == ["quoridor"]
    assert registry.get("quoridor") is game
    assert registry.view_factory("quoridor") is not None
    assert registry.all_games() == [game]


def test_duplicate_registration_raises():
    registry = GameRegistry()
    registry.register(QuoridorGame())
    with pytest.raises(ValueError):
        registry.register(QuoridorGame())


def test_unknown_key_raises():
    registry = GameRegistry()
    with pytest.raises(KeyError):
        registry.get("nope")


def test_registry_config_is_respected():
    """棋盘规格可配置：注册时传入不同构造参数即得到不同规则。"""
    registry = GameRegistry()
    registry.register(QuoridorGame(size=7, walls=5, first_player=1))
    game = registry.get("quoridor")
    state = game.initial_state()
    assert state.size == 7
    assert state.walls_left == (5, 5)
    assert state.pawns == ((3, 6), (3, 0))
    assert state.current == 1
