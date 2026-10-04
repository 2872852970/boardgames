"""昆虫棋视图：无边界画布换算、两段式点击、手牌条、像素级渲染。

重点盯的是断言数据结构**查不出来**的那一类问题：

* 世界坐标 ↔ 屏幕坐标的换算被算了两遍 / 少算一遍 —— 只在缩放或平移不为零时
  才发作，表现为"看着点在 A 格、实际落在 B 格"；
* 棋子画到了别的格子上（坐标上下翻转、半格偏移）；
* 叠层没往上抬，甲虫压在蜂后头上完全看不出来；
* 落点提示被棋子整个盖住。

所以下面的渲染断言一律**画一帧再取像素**。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from boardgames.games.hive.geometry import neighbors  # noqa: E402
from boardgames.games.hive.move import MoveMove, PassMove, PlaceMove  # noqa: E402
from boardgames.games.hive.pieces import ALL_KINDS, KIND_LABELS, Piece  # noqa: E402
from boardgames.games.hive.rules import HiveGame  # noqa: E402
from boardgames.games.hive.state import HiveState, pack  # noqa: E402
from boardgames.games.hive.view import (  # noqa: E402
    AUTO_FIT_MAX_SCALE,
    CARD_MIN_W,
    HAND_H_MAX,
    HAND_H_MIN,
    POPUP_PAD,
    POPUP_ROW_H,
    HiveView,
    body_color,
    hand_height,
    kind_tint,
    line_color,
    sprite,
)
from boardgames.ui import theme  # noqa: E402
from boardgames.ui.board_view import ViewState  # noqa: E402
from boardgames.ui.fonts import FontBook  # noqa: E402

P = Piece


def make_state(
    pieces: dict | None = None,
    *,
    current: int = 0,
    expansion: bool = False,
) -> HiveState:
    mapping = {pos: tuple(stack) for pos, stack in (pieces or {}).items()}
    return HiveState(
        stacks=pack(mapping), current=current, ply=0, expansion=expansion
    )


@pytest.fixture(autouse=True)
def _display():
    pygame.init()
    pygame.display.set_mode((160, 120))
    yield
    pygame.quit()


@pytest.fixture
def game() -> HiveGame:
    return HiveGame()


@pytest.fixture
def view() -> HiveView:
    v = HiveView()
    v.layout(pygame.Rect(20, 40, 760, 700))
    v.camera.set_viewport(v.camera_viewport())
    v.camera.reset()
    return v


@pytest.fixture
def fonts() -> FontBook:
    return FontBook()


@pytest.fixture
def surface() -> pygame.Surface:
    return pygame.Surface((820, 760))


def draw(view, fonts, surface, game, state, interactive=True):
    view.draw(
        surface, fonts, game, state, ViewState(), interactive=interactive
    )


def is_color(pixel, color, tol: int = 34) -> bool:
    return all(abs(int(a) - int(b)) <= tol for a, b in zip(pixel[:3], color, strict=False))


def is_piece(pixel, kind: str, player: int, tol: int = 40) -> bool:
    """这一像素属于「某玩家的某种虫」。

    棋子有三层颜色，取样时可能取到任意一层：身体（玩家色 + 一点虫种色）、
    线稿（玩家深色 + 大量虫种色）、外圈镶边（纯虫种色）。三层都算。
    """
    body = body_color(kind, player)
    return any(
        is_color(pixel, shade, tol)
        for shade in (
            body,
            line_color(kind, player),
            kind_tint(kind),
            theme.lighten(body, 0.40),
        )
    )


def is_player(pixel, player: int, tol: int = 40) -> bool:
    """这一像素属于该玩家的任意一种虫（虫种不知道时用它）。"""
    return any(is_piece(pixel, kind, player, tol) for kind in ALL_KINDS)


# --------------------------------------------------------------------------- #
# 布局
# --------------------------------------------------------------------------- #


def test_layout_splits_the_canvas_and_the_hand_strip(view: HiveView):
    hand_h = view.hand_rect.height
    assert hand_h == hand_height(view.area.height)
    assert view.canvas.height == view.area.height - hand_h
    assert view.canvas.bottom == view.hand_rect.top
    assert view.camera_viewport() == view.canvas
    # 手牌条上的点不该被当成画布（否则在卡片上拖动会平移棋盘）
    assert not view.canvas.collidepoint(view.hand_rect.center)
    assert view.hud_inset() >= hand_h


def test_hand_strip_height_follows_the_window():
    """矮窗口别被手牌条吃掉画布，高分屏也别显得小气。"""
    short = HiveView()
    short.layout(pygame.Rect(0, 0, 900, 560))
    tall = HiveView()
    tall.layout(pygame.Rect(0, 0, 900, 1440))
    assert HAND_H_MIN <= short.hand_rect.height < tall.hand_rect.height <= HAND_H_MAX
    # 画布永远是主角：任何窗口下都要留出至少一半给棋盘
    assert short.canvas.height > short.hand_rect.height * 4


#: 验收用的窗口尺寸（含两个极端宽高比）
WINDOW_SIZES = ((1180, 780), (1000, 640), (1600, 900), (1366, 768),
                (2560, 1440), (900, 1200), (760, 560))


def canvas_for(width: int, height: int) -> HiveView:
    """按"整窗尺寸"搭出画布（扣掉侧栏与上下留白），和真实场景一个算法。"""
    view = HiveView()
    view.layout(pygame.Rect(0, 0, width - 424, height - 52))
    view.camera.set_viewport(view.camera_viewport())
    view.camera.reset()
    return view


def assert_fits_in_canvas(view: HiveView, state, label) -> None:
    """蜂巢必须**完整**落在画布里（算错就会溢出，边缘棋子被裁掉）。"""
    bounds = view.world_bounds(state)
    x0, y0 = view.camera.world_to_screen(bounds.left, bounds.top)
    x1, y1 = view.camera.world_to_screen(bounds.right, bounds.bottom)
    assert view.canvas.collidepoint(int(x0), int(y0)), label
    assert view.canvas.collidepoint(int(x1) - 1, int(y1) - 1), label


@pytest.mark.parametrize("size", WINDOW_SIZES)
def test_auto_fit_never_zooms_past_100_percent(size):
    """开局**不许放大**：任何分辨率 / 宽高比下缩放都 <= 100%。

    这条对应一次真实事故：软上限给到 2.5 之后，开局空盘被放成 201% 贴满画布，
    玩家看到的是"界面失控了"。100% 时一枚棋直径约 70px，点得准也看得清。
    """
    width, height = size
    for state in (
        make_state(),                                     # 空盘
        make_state({(0, 0): (P(0, "queen"),)}),            # 一枚棋（包围盒退化成一个点）
        make_state({(0, 0): (P(0, "queen"),), (1, 0): (P(1, "ant"),),
                    (0, 1): (P(1, "spider"),), (-1, 1): (P(0, "beetle"),)}),
    ):
        view = canvas_for(width, height)
        view.auto_fit_camera(state)
        assert view.camera.scale <= AUTO_FIT_MAX_SCALE + 1e-6, size
        assert_fits_in_canvas(view, state, size)
        # 100% 下一个格子的外接圆还有 38px，落点提示点得中
        assert view.hex_px() >= 30, size


def test_a_big_hive_shrinks_to_fit_a_small_window():
    """大蜂巢在小窗口里要**缩**到装得下，大窗口里能保持 100% —— 这才是自适应。

    （上一条保证"不许放大"，这一条保证"该缩的时候真的缩"。两条合起来才是
    "适配不同分辨率和宽高比"。）
    """
    state = make_state({(q, 0): (P(q % 2, "ant"),) for q in range(-4, 5)})
    small = canvas_for(760, 560)
    large = canvas_for(2560, 1440)
    small.auto_fit_camera(state)
    large.auto_fit_camera(state)

    assert small.camera.scale < 1.0, small.camera.scale
    assert large.camera.scale == pytest.approx(AUTO_FIT_MAX_SCALE)
    assert large.hex_px() > small.hex_px() * 1.3, (large.hex_px(), small.hex_px())
    assert_fits_in_canvas(small, state, "small")
    assert_fits_in_canvas(large, state, "large")


def test_a_lone_piece_is_not_zoomed_to_fill_the_canvas():
    """只有一枚棋时包围盒退化成单个六边形，必须被软上限拦住。

    这条和上一条是**两头**：不设上限时一枚棋能放大到几百倍，画面上像卡死了。
    """
    state = make_state({(0, 0): [P(0, "queen")]})
    view = canvas_for(1700, 900)
    view.auto_fit_camera(state)
    assert view.camera.scale == pytest.approx(AUTO_FIT_MAX_SCALE)
    assert view.camera.scale <= 1.0  # 一枚棋也不许超过 100%


def test_world_bounds_of_an_empty_board_is_finite(view: HiveView):
    """开局一枚棋都没有 —— 包围盒不能退化成一个点（会让缩放炸掉）。"""
    bounds = view.world_bounds(make_state())
    assert bounds.width > 0 and bounds.height > 0


def test_world_bounds_covers_every_piece(view: HiveView, game: HiveGame):
    state = make_state({(0, 0): [P(0, "queen")], (4, -2): [P(1, "ant")]})
    bounds = view.world_bounds(state)
    for pos in state.occupied():
        x, y = view.world_of(pos)
        assert bounds.collidepoint(int(x), int(y))


# --------------------------------------------------------------------------- #
# 坐标换算（唯一的那个换算点）
# --------------------------------------------------------------------------- #


#: 画布内的几个格子（缩放变化时外面的会被 `pos_at` 拒绝，见下一个用例）
NEARBY = ((0, 0), (1, 0), (-1, 1), (0, -1), (1, -1), (-1, 0))


def test_screen_and_cell_round_trip_at_identity(view: HiveView):
    for pos in ((0, 0), (3, -1), (-4, 2), (4, 3)):
        assert view.pos_at(view.cell_center(pos)) == pos


def test_round_trip_survives_zoom_and_pan(view: HiveView):
    """换算写错一处时，只有缩放 / 平移不为默认值才会暴露。"""
    for scale in (0.5, 0.83, 1.06, 2.0):
        view.camera.scale = scale
        view.camera.offset = (view.canvas.centerx + 37, view.canvas.centery - 19)
        for pos in NEARBY:
            centre = view.cell_center(pos)
            assert view.canvas.collidepoint(centre), (scale, pos, centre)
            assert view.pos_at(centre) == pos, (scale, pos)


def test_far_away_cells_are_rejected_when_they_are_off_screen(view: HiveView):
    """`pos_at` 兼作"画布内"判定 —— 画布外的点不能返回一个格子。"""
    assert view.pos_at(view.cell_center((40, 40))) is None


def test_pos_at_rejects_points_outside_the_canvas(view: HiveView):
    assert view.pos_at((view.hand_rect.centerx, view.hand_rect.centery)) is None
    assert view.pos_at((view.canvas.left - 5, view.canvas.centery)) is None


def test_neighbouring_cells_do_not_overlap_in_screen_space(view: HiveView):
    """相邻格的屏幕中心必须真的相邻 —— 反了行列会让六个方向全错位。"""
    centres = [view.cell_center(n) for n in neighbors((0, 0))]
    assert len(set(centres)) == 6
    assert all(view.pos_at(c) == n for c, n in zip(centres, neighbors((0, 0)), strict=True))


# --------------------------------------------------------------------------- #
# 手牌条
# --------------------------------------------------------------------------- #


def test_hand_strip_lists_the_active_kinds(view: HiveView, game, fonts, surface):
    view._layout_cards(make_state(), 0)
    assert set(view._cards) == {"queen", "beetle", "grasshopper", "spider", "ant"}
    wide = HiveView()
    wide.layout(view.area)
    wide._layout_cards(make_state(expansion=True), 0)
    assert len(wide._cards) == 8


def test_clicking_a_hand_card_shows_the_placement_targets(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    assert view._picked == "ant"
    assert view._moves
    assert all(isinstance(m, PlaceMove) and m.kind == "ant" for m in view._moves.values())
    # 与规则层完全一致，不能多也不能少
    legal = {
        m.dest for m in game.legal_moves(state) if isinstance(m, PlaceMove) and m.kind == "ant"
    }
    assert set(view._moves) == legal


def test_clicking_the_same_card_twice_clears_the_pick(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    assert view._picked is None
    assert not view._moves


def test_an_exhausted_card_cannot_be_picked(view, game, fonts, surface):
    """蜂后已经落场 → 卡片是暗的，点了不该亮出任何落点。"""
    state = make_state({(0, 0): [P(0, "queen")], (1, 0): [P(1, "ant")]}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["queen"].center, game, state, ViewState())
    assert view._picked is None
    assert not view._moves


def test_clicking_a_target_plays_the_placement(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")]}, current=1)
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    dest = next(iter(view._moves))
    move = view.handle_click(view.cell_center(dest), game, state, ViewState())
    assert isinstance(move, PlaceMove)
    assert game.is_legal(state, move)
    # 出招后要清干净，否则下一手会拿旧落点表
    assert view._picked is None and not view._moves


# --------------------------------------------------------------------------- #
# 棋盘上选棋子
# --------------------------------------------------------------------------- #


def test_selecting_a_piece_shows_its_targets(view, game, fonts, surface):
    state = make_state(
        {
            (0, 0): [P(0, "ant")],
            (1, 0): [P(1, "ant")],
            (2, 0): [P(1, "ant")],
            (3, 0): [P(0, "queen")],
        },
        current=0,
    )
    draw(view, fonts, surface, game, state)
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    assert view._selected == (0, 0)
    legal = {
        m.dest for m in game.legal_moves(state) if getattr(m, "src", None) == (0, 0)
    }
    assert set(view._moves) == legal


def test_clicking_a_target_plays_the_move(view, game, fonts, surface):
    state = make_state(
        {
            (0, 0): [P(0, "ant")],
            (1, 0): [P(1, "ant")],
            (2, 0): [P(1, "ant")],
            (3, 0): [P(0, "queen")],
        },
        current=0,
    )
    draw(view, fonts, surface, game, state)
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    dest = sorted(view._moves)[0]
    move = view.handle_click(view.cell_center(dest), game, state, ViewState())
    assert isinstance(move, MoveMove)
    assert move.src == (0, 0) and move.dest == dest
    assert game.is_legal(state, move)


def test_clicking_the_enemy_piece_selects_nothing(view, game, fonts, surface):
    state = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0
    )
    draw(view, fonts, surface, game, state)
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    assert view._selected is None
    assert not view._moves


def test_clicking_empty_space_clears_the_selection(view, game, fonts, surface):
    state = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0
    )
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    view.handle_click(view.cell_center((-1, -1)), game, state, ViewState())
    assert view._picked is None and not view._moves


def test_a_terminal_state_swallows_clicks(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "queen")]}, current=0)
    over = HiveState(
        stacks=state.stacks, current=0, winner_player=0
    )
    draw(view, fonts, surface, game, over)
    assert view.handle_click(view._cards["ant"].center, game, over, ViewState()) is None
    assert view.handle_click(view.cell_center((0, 0)), game, over, ViewState()) is None


def test_switching_state_drops_stale_targets(view, game, fonts, surface):
    """悔棋 / 落子之后局面对象换了，旧落点表必须立刻作废。"""
    state = make_state(
        {(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0
    )
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    assert view._moves
    draw(view, fonts, surface, game, make_state({(0, 0): [P(0, "queen")]}, current=0))
    assert view._picked is None and not view._moves


# --------------------------------------------------------------------------- #
# 渲染（画一帧再取像素）
# --------------------------------------------------------------------------- #


def test_pieces_are_drawn_where_cell_center_says(view, game, fonts, surface):
    """命中测试与绘制必须走同一套换算，否则"点得中但画在别处"。"""
    state = make_state({(0, 0): [P(0, "beetle")], (2, -1): [P(1, "spider")]})
    draw(view, fonts, surface, game, state)
    for pos, player in (((0, 0), 0), ((2, -1), 1)):
        cx, cy = view.cell_center(pos)
        pixel = surface.get_at((int(cx), int(cy)))
        assert is_player(pixel, player), (pos, pixel)


def test_a_piece_does_not_bleed_into_a_neighbouring_cell(view, game, fonts, surface):
    """棋子比格子略大，但不能大到把邻格中心盖住。"""
    state = make_state({(0, 0): [P(0, "beetle")]})
    draw(view, fonts, surface, game, state)
    for n in neighbors((0, 0)):
        cx, cy = view.cell_center(n)
        assert is_color(surface.get_at((int(cx), int(cy))), theme.BOARD_BG, tol=26), n


def test_an_empty_board_still_shows_a_ground_hex(view, game, fonts, surface):
    draw(view, fonts, surface, game, make_state())
    cx, cy = view.cell_center((0, 0))
    pixel = surface.get_at((int(cx), int(cy)))
    assert not is_color(pixel, theme.BOARD_BG, tol=6)


def test_a_stack_raises_the_top_piece(view, game, fonts, surface):
    """甲虫压在蜂后头上必须往上抬 —— 否则"谁压着谁"完全看不出来。"""
    flat = make_state({(0, 0): [P(1, "queen")]})
    draw(view, fonts, surface, game, flat)
    base = view.cell_center((0, 0))
    underneath = surface.get_at((int(base[0]), int(base[1])))
    assert is_player(underneath, 1)

    stacked = make_state({(0, 0): [P(1, "queen"), P(0, "beetle")]})
    draw(view, fonts, surface, game, stacked)
    top = view.cell_center((0, 0), 1)
    assert top[1] < base[1], "叠层没有抬高"
    # 抬高之后的位置画的是上面那枚（玩家 0 的甲虫）
    assert is_player(surface.get_at((int(top[0]), int(top[1]))), 0)
    # 而格子中心已经被压在上面的甲虫盖住了 —— 画面确实变了
    assert surface.get_at((int(base[0]), int(base[1]))) != underneath


def test_a_stack_shows_a_height_badge(view, game, fonts, surface):
    """只有把层数写出来，玩家才知道这一格是"甲虫压着蜂后"还是"就一枚"。"""
    state = make_state({(0, 0): [P(1, "queen"), P(0, "beetle")]})
    draw(view, fonts, surface, game, state)
    badge = view.stack_badge_rect((0, 0))
    assert any(
        is_color(surface.get_at((x, y)), theme.WARN, tol=45)
        for x in range(badge.left, badge.right)
        for y in range(badge.top, badge.bottom)
    )
    # 角标必须留在本格六边形内 —— 探进邻格就会压住邻格的落点提示
    cx, cy = view.cell_center((0, 0))
    for corner in ((badge.left, badge.top), (badge.right - 1, badge.bottom - 1)):
        distance = ((corner[0] - cx) ** 2 + (corner[1] - cy) ** 2) ** 0.5
        assert distance <= view.hex_px(), corner


def test_the_hand_strip_is_drawn_below_the_canvas(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(1, "ant")]}, current=0)
    draw(view, fonts, surface, game, state)
    card = view._cards["ant"]
    assert is_color(surface.get_at(card.center), theme.ACCENT_DIM, tol=60) or (
        surface.get_at(card.center)[:3] != theme.BG
    )
    # 画布区域里不该出现手牌条的底色（两者不能重叠）
    bottom = pygame.Rect(view.canvas.left, view.hand_rect.top, view.canvas.width, 2)
    for x in range(bottom.left + 2, bottom.right - 2, 17):
        assert not is_color(surface.get_at((x, view.hand_rect.top + 40)), theme.BG, tol=3)


def test_target_markers_are_visible_on_the_board(view, game, fonts, surface):
    """落点提示画在棋子**之上**，否则被盖住看着像"这手不能走"。"""
    state = make_state({(0, 0): [P(0, "ant")]}, current=1)
    view._layout_cards(state, state.current)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    dest = next(iter(view._moves))
    draw(view, fonts, surface, game, state)
    cx, cy = view.cell_center(dest)
    # 提示是绿色圆环：中心是底色，环上某点必须是 OK 色
    ring_hit = any(
        is_color(surface.get_at((int(cx + dx), int(cy))), theme.OK, tol=40)
        for dx in range(-int(view.hex_px() * 0.5), int(view.hex_px() * 0.5) + 1)
    )
    assert ring_hit, f"落点 {dest} 上没看到绿色提示"


def test_clicking_a_hint_that_is_not_there_does_nothing(view, game, fonts, surface):
    """渲染出来的位置必须就是能点中的位置。"""
    state = make_state({(0, 0): [P(0, "ant")]}, current=1)
    view._layout_cards(state, state.current)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    dest = next(iter(view._moves))
    cx, cy = view.cell_center(dest)
    draw(view, fonts, surface, game, state)
    move = view.handle_click((int(cx), int(cy)), game, state, ViewState())
    assert isinstance(move, PlaceMove) and move.dest == dest


# --------------------------------------------------------------------------- #
# 框架契约
# --------------------------------------------------------------------------- #


def test_in_placement_mode_is_false(view: HiveView):
    """缺了它 ``MatchScene`` 会以为本视图支持"放墙"，右键进模式后按 V 键崩。"""
    assert view.in_placement_mode() is False


def test_hints_and_animations_are_exposed(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")]}, current=1)
    view._layout_cards(state, state.current)
    view.handle_motion(view._cards["ant"].center, game, state, ViewState())
    text, color = view.hover_hint(ViewState())
    assert "兵蚁" in text and color == theme.ACCENT
    assert "缩放" in view.hud_hint()
    assert view.idle_hint()
    assert view.hud_inset() > 0


def test_animation_runs_and_finishes(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(0, "queen"), P(1, "ant")]})
    view._state = state
    move = MoveMove(0, (0, 0), (0, -1), kind="ant", path=((0, -1),))
    view.animate(move, 200)
    assert view.is_animating()
    view.update(50.0)
    assert view.is_animating()
    view.update(400.0)
    assert not view.is_animating()


def test_a_pass_move_has_nothing_to_animate(view, game):
    view._state = make_state({(0, 0): [P(0, "queen")]})
    view.animate(PassMove(0), 200)
    assert not view.is_animating()


def test_reset_clears_everything(view, game, fonts, surface):
    state = make_state({(0, 0): [P(0, "ant")], (1, 0): [P(0, "queen"), P(1, "ant")]})
    draw(view, fonts, surface, game, state)
    view.handle_click(view._cards["ant"].center, game, state, ViewState())
    view.set_last_move(MoveMove(0, (0, 0), (0, -1)))
    view.animate(MoveMove(0, (0, 0), (0, -1)), 200)
    view.reset()
    assert view._picked is None and view._selected is None
    assert not view._moves and not view._carryable
    assert not view.is_animating()
    assert view._last_move is None


def test_camera_auto_fit_keeps_the_hive_inside_the_canvas(view, game):
    state = make_state({(0, 0): [P(0, "queen")]})
    view.auto_fit_camera(state)
    assert view.camera.auto_fit
    assert view.camera.viewport.width  # 视口已经设过
    # 只有一枚棋时不能被放大到铺满整块画布
    assert view.camera.scale <= AUTO_FIT_MAX_SCALE
    assert view.camera.scale > AUTO_FIT_MAX_SCALE / 2  # 也别缩成一小坨
    bounds = view.world_bounds(state)
    x0, y0 = view.camera.world_to_screen(bounds.left, bounds.top)
    x1, y1 = view.camera.world_to_screen(bounds.right, bounds.bottom)
    assert view.canvas.collidepoint(int((x0 + x1) / 2), int((y0 + y1) / 2))


# --------------------------------------------------------------------------- #
# 鼠妇的搬运（扩展）
# --------------------------------------------------------------------------- #


CARRY = {(0, 0): [P(0, "pillbug")], (1, 0): [P(1, "ant")], (1, -1): [P(0, "queen")]}


def _carry_view() -> HiveView:
    v = HiveView()
    v.layout(pygame.Rect(20, 40, 760, 700))
    v.camera.set_viewport(v.camera_viewport())
    v.camera.reset()
    return v


def test_pillbug_carry_takes_three_clicks(fonts, surface):
    """鼠妇的搬运必须多一次点击指定"搬谁" —— 否则落点有歧义。"""
    game = HiveGame(expansion=True)
    view = _carry_view()
    state = HiveState(
        stacks=pack({k: tuple(v) for k, v in CARRY.items()}),
        current=0,
        expansion=True,
    )
    draw(view, fonts, surface, game, state)

    # 1) 点鼠妇
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    assert view._selected == (0, 0)
    assert view._carryable == frozenset({(1, 0), (1, -1)})
    assert (0, -1) in view._moves and (0, 1) in view._moves  # 自己走一格
    assert all(isinstance(m, MoveMove) for m in view._moves.values())

    # 2) 点要搬走的那枚棋
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    assert view._carry == (1, 0)
    assert view._carryable == frozenset()
    assert all(m.dest == m.src for m in view._moves.values())  # 鼠妇自己不动

    # 3) 点落点
    dest = next(iter(view._moves))
    move = view.handle_click(view.cell_center(dest), game, state, ViewState())
    assert move is not None and move.carried == (1, 0)
    assert game.is_legal(state, move)
    after = game.apply(state, move)
    assert after.stack_at((0, 0)) == (P(0, "pillbug"),)
    assert after.top(dest) == P(1, "ant")


# --------------------------------------------------------------------------- #
# 配色：**敌我优先于虫种**
#
# 这一组是"两个玩家不好区分了"那次返工的回归测试。当时的做法是把虫种色也掺进
# 身体（0.30），整盘棋一眼看过去全是虫种色，"玩家 1 的甲虫"和"玩家 2 的鼠妇"
# 分不出来。现在的分工是：**身体 + 最外描边 = 谁的；中间镶边 + 线稿 = 什么虫**。
# --------------------------------------------------------------------------- #


def mean_color(image: pygame.Surface) -> tuple[int, int, int]:
    """贴图里不透明像素的平均色（缩略取样，够用且快）。"""
    total = [0, 0, 0]
    count = 0
    for x in range(0, image.get_width(), 2):
        for y in range(0, image.get_height(), 2):
            pixel = image.get_at((x, y))
            if pixel[3] > 200:
                for i in range(3):
                    total[i] += pixel[i]
                count += 1
    return (total[0] // count, total[1] // count, total[2] // count) if count else (0, 0, 0)


def color_distance(a, b) -> int:
    return sum(abs(int(x) - int(y)) for x, y in zip(a, b, strict=True))


def outer_edge_color(kind: str, player: int, radius: int = 80, rays: int = 36):
    """贴着剪影**最外面**那一圈的平均色。

    只沿一条射线取一个像素不行：昆虫的剪影是"腿 + 细腰"，正右方正好穿出细腰，
    取到的是抗锯齿的过渡色。所以四面八方各打一条射线，再平均。
    """
    import math

    image = sprite(kind, player, radius)
    width, height = image.get_size()
    mid = width // 2
    samples = []
    for i in range(rays):
        angle = i * math.tau / rays
        dx, dy = math.cos(angle), math.sin(angle)
        for step in range(int(width * 0.52), 1, -1):
            x, y = int(mid + dx * step), int(mid + dy * step)
            if 0 <= x < width and 0 <= y < height and image.get_at((x, y))[3] > 200:
                samples.append(image.get_at((x, y))[:3])
                break
    assert samples, (kind, player)
    return tuple(sum(s[i] for s in samples) // len(samples) for i in range(3))


def test_the_outer_edge_reads_as_the_owner_not_the_rival():
    """棋子最外那一圈，必须离**本方**的两种颜色更近（身体浅色 / 描边深色都算）。

    只要有人把玩家色去掉、或让虫种色铺到最外面，这条就红 ——
    "两个玩家不好区分了"正是这么来的。
    """
    for kind in ALL_KINDS:
        for player in (0, 1):
            edge = outer_edge_color(kind, player)
            own = min(
                color_distance(edge, theme.PLAYER_COLORS[player]),
                color_distance(edge, theme.PLAYER_DARK[player]),
            )
            rival = min(
                color_distance(edge, theme.PLAYER_COLORS[1 - player]),
                color_distance(edge, theme.PLAYER_DARK[1 - player]),
            )
            assert own < rival, (kind, player, edge, own, rival)
            assert own <= 120, (kind, player, edge, own)


def test_a_piece_carries_no_kind_colour_at_all():
    """棋盘上的棋子**一点虫种色都不掺**（虫种交给剪影 + 悬停浮窗）。

    挑的都是"离两个玩家色都远"的虫种色 —— 只要有人把虫种色重新掺回身体或
    线稿，这里立刻数得出来。
    """
    far_apart = ("grasshopper", "mosquito", "ladybug", "spider")
    for kind in far_apart:
        for player in (0, 1):
            image = sprite(kind, player, 60)
            hits = 0
            for x in range(image.get_width()):
                for y in range(image.get_height()):
                    pixel = image.get_at((x, y))
                    if pixel[3] > 200 and is_color(pixel, kind_tint(kind), 24):
                        hits += 1
            assert hits == 0, (kind, player, hits, kind_tint(kind))


def test_the_kind_tint_still_lives_on_the_hand_cards():
    """虫种色没丢掉，只是搬到了手牌卡片的底边上（那里不抢敌我信号）。"""
    view = HiveView()
    view.layout(pygame.Rect(0, 0, 900, 700))
    view.camera.set_viewport(view.camera_viewport())
    surface = pygame.Surface((900, 700))
    fonts = FontBook()
    view.draw(surface, fonts, HiveGame(), make_state(), ViewState(), interactive=False)
    for kind, rect in view._cards.items():
        stripe = pygame.Rect(rect.x + 4, rect.bottom - 4, rect.width - 8, 2)
        pixel = surface.get_at(stripe.center)
        assert is_color(pixel, kind_tint(kind), 40), (kind, pixel[:3])


def test_team_distance_beats_kind_distance():
    """同一虫种的**两个玩家**之间的平均色差，必须大于**任意两个虫种**之间的。

    把"敌我优先"写成数字：虫种色只准当配角，哪怕它更鲜艳。
    """
    per_player = {0: [], 1: []}
    same_kind: list[int] = []
    for kind in ALL_KINDS:
        a = mean_color(sprite(kind, 0, 40))
        b = mean_color(sprite(kind, 1, 40))
        per_player[0].append(a)
        per_player[1].append(b)
        same_kind.append(color_distance(a, b))

    cross_kind = [
        color_distance(per_player[player][i], per_player[player][j])
        for player in (0, 1)
        for i in range(len(ALL_KINDS))
        for j in range(i + 1, len(ALL_KINDS))
    ]
    assert min(same_kind) >= 170, same_kind
    assert min(same_kind) > max(cross_kind), (min(same_kind), max(cross_kind))


# --------------------------------------------------------------------------- #
# 提示层级 / 叠层浮窗
# --------------------------------------------------------------------------- #


def test_hints_are_drawn_after_the_pieces(view, game, fonts, surface, monkeypatch):
    """落点提示必须画在棋子**之后**。

    原先画在前面，紧贴邻格的落点会被旁边那枚棋的贴图盖掉半边 ——
    玩家看到的是"这手不能走"。
    """
    order: list[str] = []
    monkeypatch.setattr(view, "_draw_pieces", lambda *a, **k: order.append("pieces"))
    monkeypatch.setattr(view, "_draw_hints", lambda *a, **k: order.append("hints"))
    view.handle_motion((0, 0), game, make_state(), ViewState())
    draw(view, fonts, surface, game, make_state())
    assert order == ["pieces", "hints"]


def test_a_target_marker_is_painted_all_the_way_round(view, game, fonts, surface):
    """落点提示的亮环四边都要能取到提示色 —— 不管底下压着什么。"""
    state = make_state({(0, 0): (P(0, "queen"),)}, current=0)
    assert view.pick_kind("ant", game, state, ViewState()) is not None
    dest = next(iter(view._moves))
    draw(view, fonts, surface, game, state)
    cx, cy = int(view.cell_center(dest)[0]), int(view.cell_center(dest)[1])
    radius = max(5, int(view.hex_px() * 0.44))
    for dx, dy in ((radius - 1, 0), (-(radius - 1), 0), (0, radius - 1), (0, -(radius - 1))):
        # 亮环是"半径处往里 2px"画的，最外面那一像素会被抗锯齿冲淡，往里挪一点。
        pixel = surface.get_at((cx + dx, cy + dy))
        assert is_color(pixel, theme.OK, tol=70), (dx, dy, pixel[:3])


def test_hovering_a_stack_reports_what_is_underneath(view, game, fonts, surface):
    state = make_state({(0, 0): (P(0, "queen"), P(1, "beetle"))}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_motion(view.cell_center((0, 0)), game, state, ViewState())

    text, color = view.hover_hint(ViewState())
    assert "压着" in text and "蜂后" in text
    assert color == theme.WARN

    popup = view.hover_popup(state)
    assert popup is not None
    rect, rows = popup
    # 自上而下：顶上的甲虫在前，底下的蜂后在后
    assert [row[1] for row in rows] == ["beetle", "queen"]
    assert [row[0] for row in rows] == [1, 0]
    assert rows[0][2] is True and rows[-1][2] is False
    assert view.canvas.contains(rect)


def test_a_lone_piece_still_gets_a_hover_popup(view, game, fonts, surface):
    """单枚棋子也要有悬停标识 —— 棋子本身只有玩家色，虫种就靠它报。

    这是"用鼠标悬浮标识来增强区分"那条需求的直接落点：浮窗里给出
    虫种中文名 + 归属，且只有一行（不写多余的标题）。
    """
    state = make_state({(0, 0): (P(0, "spider"),)}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_motion(view.cell_center((0, 0)), game, state, ViewState())

    popup = view.hover_popup(state)
    assert popup is not None
    rect, rows = popup
    assert len(rows) == 1
    assert rows[0] == (0, "spider", True)
    assert rect.height == POPUP_PAD * 2 + POPUP_ROW_H  # 单层不占标题高度
    assert view.canvas.contains(rect)


def test_hovering_empty_space_has_no_popup(view, game, fonts, surface):
    state = make_state({(0, 0): (P(0, "queen"),)}, current=0)
    draw(view, fonts, surface, game, state)
    view.handle_motion(view.cell_center((3, 3)), game, state, ViewState())
    assert view.hover_popup(state) is None


# --------------------------------------------------------------------------- #
# 手牌条自适应
# --------------------------------------------------------------------------- #


def layout_at(width: int) -> HiveView:
    v = HiveView()
    v.layout(pygame.Rect(0, 0, width, 700))
    v.camera.set_viewport(v.camera_viewport())
    return v


@pytest.mark.parametrize("width", [340, 420, 560, 700, 900, 1400, 2200])
@pytest.mark.parametrize("expansion", [False, True])
def test_cards_never_spill_out_of_the_hand_strip(width, expansion):
    v = layout_at(width)
    state = make_state(expansion=expansion)
    v._layout_cards(state, 0)
    kinds = v.active_hand_kinds(state)
    assert tuple(v._cards) == kinds
    for kind, rect in v._cards.items():
        assert v.hand_rect.contains(rect), (width, expansion, kind, rect, v.hand_rect)
        assert rect.width >= CARD_MIN_W


def test_the_strip_sheds_decorations_before_it_squeezes_the_cards():
    """窄下去的顺序：先让右边胶囊、再让「手牌」标签、**最后**才压卡片。"""
    wide = layout_at(1000)
    wide._layout_cards(make_state(), 0)
    assert wide._show_hand_chip and wide._show_hand_label

    mid = layout_at(600)
    mid._layout_cards(make_state(), 0)
    assert not mid._show_hand_chip and mid._show_hand_label

    narrow = layout_at(360)
    narrow._layout_cards(make_state(), 0)
    assert not narrow._show_hand_chip and not narrow._show_hand_label

    for v in (wide, mid, narrow):
        assert all(v.hand_rect.contains(r) for r in v._cards.values())


# --------------------------------------------------------------------------- #
# 数字键选手牌
# --------------------------------------------------------------------------- #


def test_pick_kind_toggles_like_clicking_the_card(view, game):
    state = make_state()
    kinds = view.active_hand_kinds(state)
    target = kinds[1]

    assert view.pick_kind(target, game, state, ViewState()) == KIND_LABELS[target]
    assert view.has_selection()
    assert view._moves  # 空盘上原点周围都能落

    # 再选一次同一个 = 取消，和"再点一次卡片"一致
    assert view.pick_kind(target, game, state, ViewState()) is None
    assert not view.has_selection()

    view.clear_selection()
    assert not view.has_selection()


def test_pick_kind_rejects_an_exhausted_or_unknown_kind(view, game):
    state = make_state({(0, 0): (P(0, "queen"),)})
    assert view.pick_kind("queen", game, state, ViewState()) is None  # 蜂后就用光了
    assert view.pick_kind("dragonfly", game, state, ViewState()) is None  # 没这种虫
    assert view.pick_kind("ladybug", game, state, ViewState()) is None  # 扩展没开
    assert not view.has_selection()


# --------------------------------------------------------------------------- #
# 人机对战：手牌条钉在"我方"，不摊开对手的信息
# --------------------------------------------------------------------------- #

def test_hand_player_follows_pov_in_pve_and_current_otherwise(view):
    """``pov_player`` 是"我"哪一方：双人 / 自对弈为 None（跟随当前行动方）。"""
    assert view._hand_player(ViewState()) == 0
    assert view._hand_player(ViewState(pov_player=1)) == 1
    # 轮到谁都不影响"钉住"的视角方
    view._sync_state(make_state(current=1))
    assert view._hand_player(ViewState(pov_player=0)) == 0
    assert view._hand_player(ViewState()) == 1


def test_ai_turn_in_pve_drops_my_selection_and_hints(view, game, fonts):
    """AI 回合：人类上一手留下的选择与落点提示必须清干净。"""
    human_view = ViewState(pov_player=0)
    state = make_state()
    kind = view.active_hand_kinds(state)[0]
    view.pick_kind(kind, game, state, human_view)
    assert view._moves, "人类回合选中手牌后该有落点"

    ai_turn = make_state(current=1)
    surface = pygame.Surface((900, 700))
    view.draw(surface, fonts, game, ai_turn, human_view, interactive=False)

    assert view._picked is None and view._selected is None
    assert not view._moves, "AI 回合不该留着任何落点提示"


def test_ai_turn_in_pve_rejects_board_clicks(view, game, fonts):
    """AI 回合连点击都不该被视图接受（不依赖场景那层守卫）。"""
    ai_turn = make_state(current=1)
    human_view = ViewState(pov_player=0)
    surface = pygame.Surface((900, 700))
    view.draw(surface, fonts, game, ai_turn, human_view, interactive=False)
    kind = view.active_hand_kinds(ai_turn)[0]
    assert kind in view._cards, "手牌卡该已经排好（AI 的手牌也照常画，只是不可点）"

    assert view.handle_click(view._cards[kind].center, game, ai_turn, human_view) is None
    assert not view.has_selection()
    assert not view._moves


def test_pvp_hand_strip_still_follows_the_current_player(view):
    """双人同屏不受影响：没有 pov 时手牌条照旧跟着当前行动方。"""
    assert view._hand_player(ViewState()) == 0
    view._sync_state(make_state(current=1))
    assert view._hand_player(ViewState()) == 1
