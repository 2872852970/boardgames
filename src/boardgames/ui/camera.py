"""无边界棋盘的摄像机：平移 / 缩放 / 世界↔屏幕换算。

为什么单独抽出来
----------------
昆虫棋**没有固定棋盘** —— 蜂巢由已落的棋子长出来，可以往六个方向无限延伸。
另外三个棋类都是"缩放 = 可用区域 / 固定包围盒"，一次算完终身不变；这里不行：

* 开局只有一枚棋，包围盒退化成一个点，缩放因子会飙到几百倍；
* 每落一枚棋包围盒就变一次，整块棋盘的像素坐标跟着抖，玩家点不中格子。

所以把"世界坐标 → 屏幕坐标"的仿射变换独立成 :class:`Camera`，由玩家自己
控制（滚轮缩放 / 拖拽平移 / F 键回到蜂巢），视图只管把世界坐标交给它。

变换约定
--------
``screen = world * scale + offset``，即 :attr:`Camera.offset` 是**世界原点在
屏幕上的像素位置**。缩放以光标下的世界点为锚点（:meth:`Camera.zoom_at`），
这样"缩到哪儿"符合直觉。

自动适配
--------
:attr:`Camera.auto_fit` 为 ``True`` 时由场景每帧把内容塞进视口 —— 开局蜂巢很小，
自动放大才看得清。玩家一旦手动平移 / 缩放就置 ``False``（把控制权交给人），
按 F 或重开一局会重新置 ``True``。
"""

from __future__ import annotations

import pygame

#: 缩放范围。下限保证"整局塞得进屏幕"，上限保证不会缩到只剩一格
MIN_SCALE = 0.34
MAX_SCALE = 2.8
#: 滚轮每格缩放的倍数
ZOOM_STEP = 1.12
#: 位移超过这么多像素才算"拖拽"，否则算点击
DRAG_SLOP = 4

#: :meth:`CameraController.handle_event` 的三种返回值
NONE = "none"        # 摄像机不关心这个事件，调用方按原逻辑处理
CONSUME = "consume"  # 事件已被摄像机吃掉，不要再往下派发
CLICK = "click"      # 一次"没拖动"的左键点击 —— 调用方应当把它当点击处理


class Camera:
    """世界坐标 <-> 屏幕坐标的仿射变换 + 平移缩放。"""

    def __init__(
        self,
        min_scale: float = MIN_SCALE,
        max_scale: float = MAX_SCALE,
    ) -> None:
        self.min_scale = min_scale
        self.max_scale = max_scale
        self.scale = 1.0
        #: 世界原点的屏幕像素位置
        self.offset: tuple[float, float] = (0.0, 0.0)
        self.viewport = pygame.Rect(0, 0, 0, 0)
        #: 是否由场景每帧自动适配内容
        self.auto_fit = True

    # ------------------------------------------------------------------ #
    # 视口
    # ------------------------------------------------------------------ #

    def set_viewport(self, rect: pygame.Rect) -> None:
        """换视口时**保持画面内容不动**（窗口缩放 / 侧栏宽度变化时会调）。

        直接换掉 ``viewport`` 而不动 ``offset``，视口中心一变，整个世界就会
        跟着平移一段 —— 玩家拖好的视角在改窗口大小时会被打回原形。
        """
        rect = pygame.Rect(rect)
        old = self.viewport
        if rect == old:
            return
        if old.width and old.height:
            self.offset = (
                self.offset[0] + (rect.centerx - old.centerx),
                self.offset[1] + (rect.centery - old.centery),
            )
        self.viewport = rect

    # ------------------------------------------------------------------ #
    # 变换
    # ------------------------------------------------------------------ #

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.scale + self.offset[0], y * self.scale + self.offset[1])

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.offset[0]) / self.scale, (y - self.offset[1]) / self.scale)

    def pan(self, dx: float, dy: float) -> None:
        """按**屏幕像素**平移。"""
        self.offset = (self.offset[0] + dx, self.offset[1] + dy)

    def zoom_at(self, screen_pos: tuple[float, float], factor: float) -> None:
        """以 ``screen_pos`` 下的世界点为锚点缩放。"""
        wx, wy = self.screen_to_world(screen_pos[0], screen_pos[1])
        self.scale = max(self.min_scale, min(self.max_scale, self.scale * factor))
        self.offset = (
            screen_pos[0] - wx * self.scale,
            screen_pos[1] - wy * self.scale,
        )

    def zoom(self, factor: float) -> None:
        """以视口中心为锚点缩放（键盘 / 按钮用）。"""
        self.zoom_at(self.viewport.center, factor)

    # ------------------------------------------------------------------ #
    # 适配
    # ------------------------------------------------------------------ #

    def fit(
        self,
        world_rect: pygame.Rect | None,
        padding: float = 0.86,
        max_scale: float | None = None,
    ) -> None:
        """把 ``world_rect`` 居中并缩放到刚好装下；``None`` 表示回到世界原点。

        ``padding`` 留出边距 —— 不然新落的棋子会紧贴视口边缘。

        ``max_scale`` 是**自动适配专用**的软上限，必须比 :attr:`max_scale`
        更保守：开局那点内容实在很小，不设软上限就会把一枚棋放大到铺满整个
        画布（视觉上像"界面卡住了"）。注意它只管**上限**：不同窗口尺寸下
        该放多大，由"内容装下"自己算 —— 那才是分辨率自适应的来源。
        """
        self.auto_fit = True
        if world_rect is None or world_rect.width <= 0 or world_rect.height <= 0:
            self.reset()
            return
        scale_x = self.viewport.width * padding / world_rect.width
        scale_y = self.viewport.height * padding / world_rect.height
        ceiling = self.max_scale if max_scale is None else max_scale
        self.scale = max(self.min_scale, min(ceiling, min(scale_x, scale_y)))
        self.offset = (
            self.viewport.centerx - (world_rect.x + world_rect.width / 2) * self.scale,
            self.viewport.centery - (world_rect.y + world_rect.height / 2) * self.scale,
        )

    def reset(self) -> None:
        """回到"世界原点在视口中心、缩放 1:1"。"""
        self.scale = 1.0
        self.offset = (float(self.viewport.centerx), float(self.viewport.centery))
        self.auto_fit = True

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def visible_world_rect(self) -> pygame.Rect:
        """当前视口覆盖的世界范围（绘制时用来剔除屏幕外的东西）。"""
        x0, y0 = self.screen_to_world(self.viewport.left, self.viewport.top)
        x1, y1 = self.screen_to_world(self.viewport.right, self.viewport.bottom)
        return pygame.Rect(int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))

    def contains(self, world_rect: pygame.Rect) -> bool:
        """``world_rect`` 是否完整落在视口内（用来判断要不要自动拉回）。"""
        return self.viewport.contains(self._to_screen_rect(world_rect))

    def _to_screen_rect(self, world_rect: pygame.Rect) -> pygame.Rect:
        x0, y0 = self.world_to_screen(world_rect.left, world_rect.top)
        x1, y1 = self.world_to_screen(world_rect.right, world_rect.bottom)
        return pygame.Rect(int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))


class CameraController:
    """把鼠标事件翻译成摄像机的平移 / 缩放，并**判定点击与拖拽**。

    难点：``MOUSEBUTTONDOWN`` 那一刻还分不清玩家是想点棋子还是想拖画布。
    所以左键按下时先"扣住"事件，等 ``MOUSEBUTTONUP`` 再根据累计位移裁决：

    * 位移 > :data:`DRAG_SLOP` → 这一串事件是拖拽，松手返回 ``CONSUME``；
    * 否则 → 返回 ``CLICK``，由调用方补一次点击派发。

    这样"点一下"与"拖一下"互不干扰，也不会出现"手抖了一下就走错子"。
    """

    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        self._press: tuple[int, int] | None = None
        self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    @property
    def pressed(self) -> bool:
        return self._press is not None

    def cancel(self) -> None:
        """丢弃进行中的手势（换局 / 悔棋 / 场景切换时调）。"""
        if self._dragging:
            _set_cursor("arrow")
        self._press = None
        self._dragging = False

    def handle_event(self, event: pygame.event.Event) -> str:
        camera = self.camera
        viewport = camera.viewport

        if event.type == pygame.MOUSEWHEEL:
            # MOUSEWHEEL 未必带 ``pos``（pygame 版本相关），带就用带的，
            # 没有才回退到"问鼠标现在在哪"。
            pos = getattr(event, "pos", None) or pygame.mouse.get_pos()
            if not viewport.collidepoint(pos):
                return NONE
            camera.auto_fit = False
            camera.zoom_at(pos, ZOOM_STEP ** event.y)
            return CONSUME

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2):
            if not viewport.collidepoint(event.pos):
                return NONE
            self._press = event.pos
            self._dragging = False
            return CONSUME

        if event.type == pygame.MOUSEMOTION and self._press is not None:
            # 按键在视口外松掉了（pygame 只在窗口内给 BUTTONUP）
            if not (event.buttons[0] or event.buttons[1]):
                self.cancel()
                return NONE
            if not self._dragging:
                dx = event.pos[0] - self._press[0]
                dy = event.pos[1] - self._press[1]
                if dx * dx + dy * dy <= DRAG_SLOP * DRAG_SLOP:
                    return CONSUME  # 还在"可能是点击"的范围内，先扣着
                self._dragging = True
                _set_cursor("move")
            camera.auto_fit = False
            camera.pan(event.rel[0], event.rel[1])
            return CONSUME

        if event.type == pygame.MOUSEBUTTONUP and self._press is not None:
            was_drag = self._dragging
            self.cancel()
            if was_drag:
                return CONSUME
            return CLICK if event.button == 1 else CONSUME

        return NONE


def _set_cursor(kind: str) -> None:
    """拖拽时换个光标。失败就拉倒 —— 光标只是锦上添花，不该影响主流程。"""
    try:
        which = pygame.SYSTEM_CURSOR_SIZEALL if kind == "move" else pygame.SYSTEM_CURSOR_ARROW
        pygame.mouse.set_cursor(which)
    except (pygame.error, AttributeError):  # pragma: no cover
        pass
