"""摄像机：世界↔屏幕变换、缩放锚点、点击 / 拖拽裁决。

摄像机是给"无边界棋盘"用的通用能力，所以它自己不依赖任何棋类 ——
这里的用例也一律用人造的 ``pygame.event.Event``，不启动窗口。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from boardgames.ui.camera import (  # noqa: E402
    CLICK,
    CONSUME,
    DRAG_SLOP,
    MAX_SCALE,
    MIN_SCALE,
    NONE,
    Camera,
    CameraController,
)


@pytest.fixture(autouse=True)
def _display():
    pygame.init()
    pygame.display.set_mode((240, 180))
    yield
    pygame.quit()


def make_camera(rect=(100, 50, 400, 300)) -> Camera:
    camera = Camera()
    camera.set_viewport(pygame.Rect(rect))
    camera.reset()
    return camera


def wheel(y: int, pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEWHEEL, y=y, pos=pos)


def down(button: int, pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=button, pos=pos
    )


def up(button: int, pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos)


def motion(pos: tuple[int, int], rel: tuple[int, int], buttons=(1, 0, 0)) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=rel, buttons=buttons)


# --------------------------------------------------------------------------- #
# 变换
# --------------------------------------------------------------------------- #


def test_screen_and_world_round_trip():
    camera = make_camera()
    camera.scale = 1.7
    camera.offset = (33.0, -12.0)
    for point in ((0.0, 0.0), (10.0, -4.0), (-123.5, 77.25)):
        screen = camera.world_to_screen(*point)
        back = camera.screen_to_world(*screen)
        assert back[0] == pytest.approx(point[0])
        assert back[1] == pytest.approx(point[1])


def test_offset_is_where_the_world_origin_lands_on_screen():
    camera = make_camera()
    assert camera.world_to_screen(0.0, 0.0) == camera.offset
    # reset() 把世界原点摆到视口正中
    assert camera.offset == (300.0, 200.0)


def test_pan_moves_by_screen_pixels():
    camera = make_camera()
    before = camera.world_to_screen(4.0, 4.0)
    camera.pan(25, -40)
    after = camera.world_to_screen(4.0, 4.0)
    assert after[0] - before[0] == pytest.approx(25)
    assert after[1] - before[1] == pytest.approx(-40)


def test_zoom_keeps_the_world_point_under_the_cursor():
    """以光标为锚点 —— 缩放前后光标下还是同一个世界点，才符合直觉。"""
    camera = make_camera()
    cursor = (420, 130)
    before = camera.screen_to_world(*cursor)
    camera.zoom_at(cursor, 1.6)
    after = camera.screen_to_world(*cursor)
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])
    assert camera.scale > 1.0


def test_zoom_out_then_in_is_not_quite_a_round_trip_but_stays_close():
    """来回缩放会被上下限夹住，但锚点始终不跑。"""
    camera = make_camera()
    for _ in range(6):
        camera.zoom_at((200, 150), 0.8)
        camera.zoom_at((200, 150), 1.25)
    assert MIN_SCALE <= camera.scale <= MAX_SCALE


def test_scale_is_clamped():
    camera = make_camera()
    camera.zoom_at(camera.viewport.center, 100.0)
    assert camera.scale == pytest.approx(MAX_SCALE)
    camera.zoom_at(camera.viewport.center, 0.0001)
    assert camera.scale == pytest.approx(MIN_SCALE)


def test_zoom_without_an_anchor_uses_the_viewport_center():
    camera = make_camera()
    centre_before = camera.screen_to_world(*camera.viewport.center)
    camera.zoom(1.5)
    assert camera.screen_to_world(*camera.viewport.center) == pytest.approx(centre_before)


# --------------------------------------------------------------------------- #
# 适配
# --------------------------------------------------------------------------- #


def test_fit_centres_the_content():
    camera = make_camera()
    camera.fit(pygame.Rect(-200, -100, 400, 200))
    left, top = camera.world_to_screen(-200, -100)
    right, bottom = camera.world_to_screen(200, 100)
    assert (left + right) / 2 == pytest.approx(camera.viewport.centerx)
    assert (top + bottom) / 2 == pytest.approx(camera.viewport.centery)


def test_fit_leaves_a_margin():
    camera = make_camera()
    camera.fit(pygame.Rect(0, 0, 500, 500))
    left, top = camera.world_to_screen(0, 0)
    right, bottom = camera.world_to_screen(500, 500)
    assert right - left < camera.viewport.width
    assert bottom - top < camera.viewport.height
    assert right - left > camera.viewport.width * 0.5  # 但也别缩得太小


def test_fit_of_a_degenerate_box_falls_back_to_the_origin():
    """开局一枚棋时包围盒是单点 —— 除零会让 scale 变成 inf/NaN。"""
    camera = make_camera()
    camera.fit(pygame.Rect(0, 0, 0, 0))
    assert camera.scale == 1.0
    assert camera.offset == (300.0, 200.0)


def test_fit_of_an_empty_board_is_finite():
    camera = make_camera()
    camera.fit(None)
    assert MIN_SCALE <= camera.scale <= MAX_SCALE


def test_fit_rearms_auto_fit():
    camera = make_camera()
    camera.auto_fit = False
    camera.fit(pygame.Rect(0, 0, 40, 40))
    assert camera.auto_fit is True


def test_fit_clamps_the_scale_for_a_tiny_box():
    camera = make_camera()
    camera.fit(pygame.Rect(0, 0, 1, 1))
    assert camera.scale == pytest.approx(MAX_SCALE)


def test_visible_world_rect_grows_when_zooming_out():
    camera = make_camera()
    near = camera.visible_world_rect()
    camera.zoom(0.5)
    far = camera.visible_world_rect()
    assert far.width > near.width and far.height > near.height


def test_set_viewport_keeps_the_picture_put():
    """改窗口大小不该把玩家拖好的视角打回原形。"""
    camera = make_camera((100, 50, 400, 300))
    camera.auto_fit = False
    marker = (5.0, 7.0)
    before = camera.world_to_screen(*marker)
    camera.set_viewport(pygame.Rect(100, 50, 520, 360))
    after = camera.world_to_screen(*marker)
    # 视口左上角没动，画面整体不该跳；只有中心变了才需要补偿
    assert after[0] == pytest.approx(before[0] + 60)
    assert after[1] == pytest.approx(before[1] + 30)


# --------------------------------------------------------------------------- #
# 手势：点击 vs 拖拽
# --------------------------------------------------------------------------- #


def test_a_clean_press_and_release_is_a_click():
    camera = make_camera()
    controller = CameraController(camera)
    pos = (250, 150)
    assert controller.handle_event(down(1, pos)) == CONSUME
    assert controller.handle_event(up(1, pos)) == CLICK
    assert camera.offset == (300.0, 200.0)  # 一下都没动过


def test_a_small_jitter_is_still_a_click():
    """手抖一两个像素不算拖拽 —— 否则"点格子"会变成"走错子"。"""
    camera = make_camera()
    controller = CameraController(camera)
    pos = (250, 150)
    controller.handle_event(down(1, pos))
    controller.handle_event(motion((pos[0] + DRAG_SLOP, pos[1]), (DRAG_SLOP, 0)))
    assert controller.handle_event(up(1, (pos[0] + DRAG_SLOP, pos[1]))) == CLICK


def test_a_real_drag_pans_and_swallows_the_release():
    camera = make_camera()
    controller = CameraController(camera)
    pos = (250, 150)
    controller.handle_event(down(1, pos))
    controller.handle_event(motion((pos[0] + 30, pos[1]), (30, 0)))
    assert controller.dragging
    assert controller.handle_event(up(1, (pos[0] + 30, pos[1]))) == CONSUME
    assert camera.offset[0] == pytest.approx(330.0)
    assert not controller.dragging


def test_dragging_turns_off_auto_fit():
    camera = make_camera()
    controller = CameraController(camera)
    assert camera.auto_fit is True
    controller.handle_event(down(1, (250, 150)))
    controller.handle_event(motion((280, 150), (30, 0)))
    assert camera.auto_fit is False


def test_the_middle_button_never_produces_a_click():
    camera = make_camera()
    controller = CameraController(camera)
    assert controller.handle_event(down(2, (250, 150))) == CONSUME
    assert controller.handle_event(up(2, (250, 150))) == CONSUME


def test_events_outside_the_viewport_are_ignored():
    camera = make_camera()
    controller = CameraController(camera)
    assert controller.handle_event(down(1, (10, 10))) == NONE
    assert controller.handle_event(motion((12, 12), (2, 2))) == NONE


def test_wheel_zooms_at_the_cursor_and_is_consumed():
    camera = make_camera()
    controller = CameraController(camera)
    target = (350, 120)
    pygame.mouse.set_pos(target)
    before = camera.screen_to_world(*target)
    assert controller.handle_event(wheel(1, target)) == CONSUME
    assert camera.scale > 1.0
    assert camera.screen_to_world(*target) == pytest.approx(before)


def test_wheel_outside_the_viewport_is_ignored():
    camera = make_camera()
    controller = CameraController(camera)
    pygame.mouse.set_pos((5, 5))
    assert controller.handle_event(wheel(1, (5, 5))) == NONE
    assert camera.scale == 1.0


def test_a_release_outside_the_window_resets_the_gesture():
    """按键拖到视口外松手：pygame 不给 BUTTONUP，靠 buttons 全 0 兜底。"""
    camera = make_camera()
    controller = CameraController(camera)
    controller.handle_event(down(1, (250, 150)))
    assert controller.handle_event(motion((260, 150), (10, 0), buttons=(0, 0, 0))) == NONE
    assert not controller.pressed
    assert not controller.dragging


def test_cancel_drops_a_pending_gesture():
    camera = make_camera()
    controller = CameraController(camera)
    controller.handle_event(down(1, (250, 150)))
    controller.cancel()
    assert not controller.pressed
    assert controller.handle_event(up(1, (250, 150))) == NONE


def test_unrelated_events_pass_through():
    camera = make_camera()
    controller = CameraController(camera)
    assert controller.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f)) == NONE
    # 右键不归摄像机管（留给"放墙模式"）
    assert controller.handle_event(down(3, (250, 150))) == NONE
