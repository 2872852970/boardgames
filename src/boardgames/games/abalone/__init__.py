"""大力士棋（Abalone）。

与步步为营、重力四子棋一样遵守框架的分层铁律：本包只依赖 ``core``，
不 import pygame、不 import ai、不 import ui。
（``view.py`` 是唯一碰 pygame 的模块，注册表在 :mod:`boardgames.app` 里
单独 ``register_view``，所以本文件不会把它拖进来。）
"""

from boardgames.games.abalone.layouts import (
    ABALONE_SETUPS,
    DEFAULT_SETUP,
    MARBLES_PER_PLAYER,
    SETUP_LABELS,
    WIN_OUT,
)
from boardgames.games.abalone.move import AbaloneMove
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState, initial_state

__all__ = [
    "AbaloneGame",
    "AbaloneState",
    "AbaloneMove",
    "initial_state",
    "ABALONE_SETUPS",
    "SETUP_LABELS",
    "DEFAULT_SETUP",
    "MARBLES_PER_PLAYER",
    "WIN_OUT",
]
