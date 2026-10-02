"""绘制工具：圆角矩形、柔和阴影、抗锯齿文字、渐变。"""

from __future__ import annotations

from typing import Literal

import pygame

from boardgames.ui import theme

Align = Literal["left", "center", "right"]
Baseline = Literal["top", "middle", "bottom"]


def rounded_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color: tuple[int, ...],
    radius: int = theme.RADIUS,
    width: int = 0,
) -> None:
    radius = max(0, min(radius, rect.width // 2, rect.height // 2))
    pygame.draw.rect(surface, color, rect, width, border_radius=radius)


def soft_shadow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int = theme.RADIUS,
    spread: int = 3,
    offset: tuple[int, int] = (0, 3),
) -> None:
    """用几层递减的深色圆角矩形模拟柔和阴影（pygame 没有原生阴影）。"""
    for i in range(spread, 0, -1):
        alpha = 70 // i
        if alpha <= 0:
            continue
        layer = pygame.Surface((rect.width + i * 4, rect.height + i * 4), pygame.SRCALPHA)
        rounded_rect(
            layer,
            pygame.Rect(0, 0, layer.get_width(), layer.get_height()),
            (*theme.SHADOW, alpha),
            radius + i * 2,
        )
        surface.blit(layer, (rect.x + offset[0] - i * 2, rect.y + offset[1] - i * 2))


def panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    color: tuple[int, int, int] = theme.PANEL,
    radius: int = theme.RADIUS,
    border: tuple[int, int, int] | None = theme.BORDER_SOFT,
    shadow: bool = True,
) -> None:
    if shadow:
        soft_shadow(surface, rect, radius)
    rounded_rect(surface, rect, color, radius)
    if border is not None:
        rounded_rect(surface, rect, border, radius, width=1)


def vertical_gradient(
    surface: pygame.Surface, rect: pygame.Rect, top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> None:
    if rect.height <= 0 or rect.width <= 0:
        return
    strip = pygame.Surface((1, rect.height))
    for y in range(rect.height):
        strip.set_at((0, y), theme.mix(top, bottom, y / max(1, rect.height - 1)))
    surface.blit(pygame.transform.scale(strip, (rect.width, rect.height)), rect.topleft)


def text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    content: str,
    pos: tuple[int, int],
    color: tuple[int, int, int] = theme.TEXT,
    *,
    align: Align = "left",
    baseline: Baseline = "top",
) -> pygame.Rect:
    """绘制抗锯齿文字并返回其矩形。"""
    image = font.render(content, True, color)
    rect = image.get_rect()
    if align == "left":
        rect.left = pos[0]
    elif align == "center":
        rect.centerx = pos[0]
    else:
        rect.right = pos[0]
    if baseline == "top":
        rect.top = pos[1]
    elif baseline == "middle":
        rect.centery = pos[1]
    else:
        rect.bottom = pos[1]
    surface.blit(image, rect)
    return rect


def circle_glow(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    layers: int = 5,
    max_alpha: int = 90,
) -> None:
    """在圆点外围叠加几层半透明圆，做出发光效果。"""
    for i in range(layers, 0, -1):
        alpha = max(6, max_alpha // i)
        r = radius + i * 2
        layer = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*color, alpha), (r, r), r)
        surface.blit(layer, (center[0] - r, center[1] - r))


def truncate(font: pygame.font.Font, content: str, max_width: int) -> str:
    """按像素宽度截断文字并加省略号。"""
    if font.size(content)[0] <= max_width:
        return content
    ellipsis = "…"
    out = content
    while out and font.size(out + ellipsis)[0] > max_width:
        out = out[:-1]
    return out + ellipsis
