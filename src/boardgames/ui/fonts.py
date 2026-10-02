"""中文字体加载与缓存。

pygame 的 ``SysFont`` 名称匹配在 Windows 上并不可靠，因此**优先按文件路径加载**
系统里的中文字体；全部失败时降级为 ASCII 提示。
"""

from __future__ import annotations

from pathlib import Path

import pygame

#: (常规, 粗体) 候选字体文件，按优先级排列
FONT_PAIRS: tuple[tuple[str, str], ...] = (
    ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"),     # 微软雅黑
    ("C:/Windows/Fonts/Deng.ttf", "C:/Windows/Fonts/Dengb.ttf"),      # 等线
    ("C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simhei.ttf"),   # 黑体
    ("C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/simsun.ttc"),   # 宋体
)

#: ``pygame.font.match_font`` 的兜底名字
MATCH_NAMES = ["microsoftyahei", "msyh", "simhei", "dengxian", "simsun", "notosanscjksc"]


def _pick_file() -> tuple[str | None, str | None]:
    for regular, bold in FONT_PAIRS:
        if Path(regular).exists():
            return regular, (bold if Path(bold).exists() else regular)
    found = pygame.font.match_font(",".join(MATCH_NAMES))
    if found:
        return found, found
    return None, None


class FontBook:
    """按 ``(尺寸, 是否粗体)`` 缓存 ``pygame.font.Font``。

    每帧重建 Font 是常见性能坑，这里必须缓存。
    """

    def __init__(self) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        self.regular_path, self.bold_path = _pick_file()
        self._cache: dict[tuple[int, bool], pygame.font.Font] = {}

    @property
    def has_cjk(self) -> bool:
        return self.regular_path is not None

    def get(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (int(size), bool(bold))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        path = self.bold_path if bold else self.regular_path
        font = pygame.font.Font(path, size) if path is not None else pygame.font.Font(None, size)
        if bold and path == self.regular_path:
            font.set_bold(True)
        self._cache[key] = font
        return font
