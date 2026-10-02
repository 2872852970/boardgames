"""内置棋类游戏包。新增棋类时在本目录建子包，并在 core.registry 中注册。"""

from boardgames.games.quoridor.rules import QuoridorGame

__all__ = ["QuoridorGame"]
