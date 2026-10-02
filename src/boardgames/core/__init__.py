"""通用游戏抽象层（游戏无关）。

本包只允许依赖标准库，禁止 import pygame 或任何具体游戏实现。
"""

from boardgames.core.game import Game
from boardgames.core.move import Move
from boardgames.core.player import PlayerId, PlayerMeta
from boardgames.core.registry import GameRegistry
from boardgames.core.result import Termination
from boardgames.core.state import State

__all__ = [
    "Game",
    "GameRegistry",
    "Move",
    "PlayerId",
    "PlayerMeta",
    "State",
    "Termination",
]
