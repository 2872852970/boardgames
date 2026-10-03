"""大力士棋测试夹具（造局面的工具见 :mod:`aba_helpers`）。"""

from __future__ import annotations

import pytest

from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState


@pytest.fixture
def game() -> AbaloneGame:
    return AbaloneGame()


@pytest.fixture
def standard() -> AbaloneState:
    """标准开局的局面。"""
    return AbaloneGame().initial_state()
