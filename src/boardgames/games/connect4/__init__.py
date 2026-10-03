"""重力四子棋（Connect Four）。

与步步为营一样遵守框架的分层铁律：本包只依赖 ``core``，不 import pygame、
不 import ai、不 import ui。
"""

from boardgames.games.connect4.move import DropMove
from boardgames.games.connect4.rules import Connect4Game
from boardgames.games.connect4.state import (
    CONNECT_TO,
    DEFAULT_COLS,
    DEFAULT_ROWS,
    Connect4State,
    initial_state,
)

__all__ = [
    "Connect4Game",
    "Connect4State",
    "DropMove",
    "initial_state",
    "CONNECT_TO",
    "DEFAULT_COLS",
    "DEFAULT_ROWS",
]
