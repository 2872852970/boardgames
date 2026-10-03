"""UI 测试公用夹具。

用 SDL 的 dummy 视频驱动，因此不需要真实显示器。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from boardgames.app import build_registry  # noqa: E402
from boardgames.settings import Settings  # noqa: E402
from boardgames.ui.window import GameWindow  # noqa: E402


@pytest.fixture
def make_window(tmp_path):
    created: list[GameWindow] = []

    def _make(**overrides) -> GameWindow:
        # 约定：``game_key`` / ``start_scene`` 是窗口构造参数，其余覆盖写进 settings
        window_kwargs = {
            key: overrides.pop(key)
            for key in ("game_key", "start_scene")
            if key in overrides
        }
        settings = Settings(tmp_path / "settings.json")
        for key, value in overrides.items():
            settings.values[key] = value
        window = GameWindow(settings, build_registry(), offscreen=True, **window_kwargs)
        created.append(window)
        return window

    yield _make
    for _window in created:
        if pygame.get_init():
            pygame.quit()
