"""深色现代主题：色板、圆角、间距。"""

from __future__ import annotations

RGB = tuple[int, int, int]

# --------------------------------------------------------------------------- #
# 色板（深色）
# --------------------------------------------------------------------------- #

BG: RGB = (23, 24, 31)
BG_ALT: RGB = (28, 30, 38)
PANEL: RGB = (36, 38, 48)
PANEL_ALT: RGB = (46, 49, 62)
PANEL_HOVER: RGB = (56, 60, 75)
BORDER: RGB = (58, 62, 78)
BORDER_SOFT: RGB = (46, 50, 63)

TEXT: RGB = (231, 233, 240)
TEXT_DIM: RGB = (146, 152, 168)
TEXT_FAINT: RGB = (104, 110, 126)

ACCENT: RGB = (79, 156, 249)
ACCENT_HOVER: RGB = (110, 175, 255)
ACCENT_DIM: RGB = (46, 92, 152)

OK: RGB = (61, 214, 140)
BAD: RGB = (255, 92, 92)
WARN: RGB = (240, 185, 90)

WALL: RGB = (232, 196, 90)
WALL_EDGE: RGB = (255, 226, 140)
WALL_SHADOW: RGB = (120, 92, 20)

BOARD_BG: RGB = (32, 34, 43)
CELL: RGB = (42, 45, 57)
CELL_ALT: RGB = (46, 50, 63)
GOAL_TINT_P0: RGB = (58, 50, 36)
GOAL_TINT_P1: RGB = (36, 46, 66)

SHADOW: RGB = (12, 13, 17)

P0: RGB = (240, 185, 90)
P0_DARK: RGB = (176, 128, 44)
P1: RGB = (91, 141, 239)
P1_DARK: RGB = (52, 88, 168)

HINT_DOT: RGB = (120, 200, 255)
SELECT_RING: RGB = (255, 255, 255)

# --------------------------------------------------------------------------- #
# 尺寸
# --------------------------------------------------------------------------- #

WINDOW_W = 1180
WINDOW_H = 780
SIDEBAR_W = 372
PADDING = 18

#: 窗口尺寸下限；实际尺寸还会被屏幕可用区域裁剪（见 window.choose_window_size）
MIN_WINDOW_W = 760
MIN_WINDOW_H = 560
#: 侧栏在小窗口下允许收窄到这里
SIDEBAR_MIN_W = 316

RADIUS = 10
RADIUS_SM = 6
RADIUS_PILL = 999

FPS = 60

#: 棋盘区域留给棋盘的边长
BOARD_MARGIN = 26

PLAYER_COLORS: tuple[RGB, RGB] = (P0, P1)
PLAYER_DARK: tuple[RGB, RGB] = (P0_DARK, P1_DARK)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def darken(color: RGB, t: float) -> RGB:
    return mix(color, (0, 0, 0), t)


def lighten(color: RGB, t: float) -> RGB:
    return mix(color, (255, 255, 255), t)


def with_alpha(color: RGB, alpha: int) -> tuple[int, int, int, int]:
    return (color[0], color[1], color[2], max(0, min(255, alpha)))
