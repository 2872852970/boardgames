"""昆虫棋测试夹具（造局面的工具见 :mod:`hive_build`）。"""

from __future__ import annotations

import pytest

from boardgames.games.hive.rules import HiveGame
from boardgames.games.hive.state import HiveState, initial_state


@pytest.fixture
def game() -> HiveGame:
    """基础五虫的昆虫棋。"""
    return HiveGame()


@pytest.fixture
def game_x() -> HiveGame:
    """带官方扩展三虫（瓢虫 / 蚊子 / 鼠妇）的昆虫棋。"""
    return HiveGame(expansion=True)


@pytest.fixture
def empty() -> HiveState:
    """空盘（轮到玩家 0，第一枚必须落在世界原点）。"""
    return initial_state()
