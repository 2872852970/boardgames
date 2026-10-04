"""点格棋（Dots and Boxes）。"""

from boardgames.games.dotsboxes.move import EdgeMove
from boardgames.games.dotsboxes.rules import DotsBoxesGame
from boardgames.games.dotsboxes.state import DEFAULT_SIZE, DotsBoxesState, initial_state

__all__ = [
    "DotsBoxesGame",
    "DotsBoxesState",
    "EdgeMove",
    "initial_state",
    "DEFAULT_SIZE",
]
