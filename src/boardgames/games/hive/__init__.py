"""昆虫棋（Hive）。

与步步为营、重力四子棋、大力士棋一样遵守框架的分层铁律：本包只依赖 ``core``，
不 import pygame、不 import ai、不 import ui。
（``view.py`` 是唯一碰 pygame 的模块，注册表在 :mod:`boardgames.app` 里
单独 ``register_view``，所以本文件不会把它拖进来。）
"""

from boardgames.games.hive.geometry import DIRECTIONS, GATES, Pos, neighbors
from boardgames.games.hive.heuristic import DEFAULT_WEIGHTS
from boardgames.games.hive.move import MoveMove, PassMove, PillbugMove, PlaceMove
from boardgames.games.hive.pieces import (
    ALL_KINDS,
    BASE_KINDS,
    EXTRA_KINDS,
    KIND_LABELS,
    Piece,
)
from boardgames.games.hive.rules import HiveGame
from boardgames.games.hive.state import HiveState, initial_state

__all__ = [
    "HiveGame",
    "HiveState",
    "MoveMove",
    "PassMove",
    "PillbugMove",
    "PlaceMove",
    "Piece",
    "initial_state",
    "neighbors",
    "Pos",
    "DIRECTIONS",
    "GATES",
    "ALL_KINDS",
    "BASE_KINDS",
    "EXTRA_KINDS",
    "KIND_LABELS",
    "DEFAULT_WEIGHTS",
]
