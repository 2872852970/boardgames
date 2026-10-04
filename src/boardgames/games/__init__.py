"""内置棋类游戏包。新增棋类时在本目录建子包，并在 core.registry 中注册。"""

from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.connect4.rules import Connect4Game
from boardgames.games.dotsboxes.rules import DotsBoxesGame
from boardgames.games.hive.rules import HiveGame
from boardgames.games.mancala.rules import MancalaGame
from boardgames.games.quoridor.rules import QuoridorGame

__all__ = ["AbaloneGame", "QuoridorGame", "Connect4Game", "HiveGame", "DotsBoxesGame", "MancalaGame"]
