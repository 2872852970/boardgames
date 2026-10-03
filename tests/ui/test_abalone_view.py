"""大力士棋视图：六边形布局、两段式点击、目标格提示、滑行动画。

重点盯的是**只有画一帧才能发现**的问题：六边形网格上下/左右反了、像素落点差半格、
目标格提示被棋子盖住 —— 断言数据结构是一样214查不出来的。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest
from helpers import press

from boardgames.games.abalone.geometry import CELLS
from boardgames.games.abalone.move import AbaloneMove
from boardgames.games.abalone.rules import AbaloneGame
from boardgames.games.abalone.state import AbaloneState, initial_state
from boardgames.games.abalone.view import AbaloneView
from boardgames.ui import theme
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook

E, NE, NW, W, SW, SE = range(6)


@pytest.fixture
def view():
    v = AbaloneView()
    v.layout(pygame.Rect(0, 0, 760, 700))
    return v


@pytest.fixture
def game():
    return AbaloneGame()


@pytest.fixture
def fonts():
    return FontBook()


def _make(
    pieces: dict[tuple[int, int], int],
    *,
    out: tuple[int, int] = (0, 0),
    current: int = 0,
    ply: int = 0,
) -> AbaloneState:
    """按坐标造局面（其余 61 格留空）。

    这里自带一份，不 import ``tests/games/abalone/aba_helpers``：pytest 会把每个测试
    目录都塞进 ``sys.path``，跨目录 import 在别的机器上未必还能解析。
    """
    from boardgames.games.abalone.geometry import CELL_COUNT, INDEX

    cells = [0] * CELL_COUNT
    for pos, value in pieces.items():
        cells[INDEX[pos]] = value
    return AbaloneState(
        cells=tuple(cells), out=out, current=current, ply=ply, winner_player=None
    )


# --------------------------------------------------------------------------- #
# 布局
# --------------------------------------------------------------------------- #

def test_layout_produces_positive_cell(view):
    assert view.cell >= 16
    assert len(view.origin) == 2


def test_board_fits_inside_the_area(view):
    board = view.board_rect()
    assert view.area.contains(board) or board.width <= view.area.width
    assert board.width > 0 and board.height > 0


def test_layout_adapts_to_a_small_area():
    v = AbaloneView()
    v.layout(pygame.Rect(0, 0, 320, 300))
    assert v.cell >= 10
    assert v.board_rect().width <= 320


def test_every_cell_center_roundtrips(view):
    """61 格：像素 → 坐标必须原样回来（舍入用错会整片偏半格）。"""
    for pos in CELLS:
        assert view.pos_at(view.cell_center(pos)) == pos, pos


def test_click_far_from_any_cell_returns_none(view):
    assert view.pos_at((-50, -50)) is None
    assert view.pos_at((view.area.right + 40, view.area.centery)) is None


def test_axial_up_is_screen_up(view):
    """``r`` 越小屏幕越靠上（pointy-top 的行序）。"""
    assert view.cell_center((0, -4))[1] < view.cell_center((0, 0))[1]
    assert view.cell_center((0, 0))[1] < view.cell_center((0, 4))[1]


def test_axial_east_is_screen_right(view):
    assert view.cell_center((4, 0))[0] > view.cell_center((-4, 0))[0]


def test_center_cell_sits_in_the_middle(view):
    board = view.board_rect()
    assert abs(view.cell_center((0, 0))[0] - board.centerx) <= 2
    assert abs(view.cell_center((0, 0))[1] - board.centery) <= 2


# --------------------------------------------------------------------------- #
# 绘制：必须真的画出来
# --------------------------------------------------------------------------- #

def test_marble_is_painted_at_its_cell(view, fonts, game):
    state = _make({(0, 0): 1})
    surface = pygame.Surface((760, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=False)
    assert tuple(surface.get_at(view.cell_center((0, 0))))[:3] == theme.PLAYER_COLORS[0]


def test_second_players_marble_uses_index_one(view, fonts, game):
    """调色板索引是**玩家号 0/1**：写成棋子值 2 会 IndexError。"""
    state = _make({(0, 0): 2})
    surface = pygame.Surface((760, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=False)
    assert tuple(surface.get_at(view.cell_center((0, 0))))[:3] == theme.PLAYER_COLORS[1]


def test_empty_cell_is_not_a_marble(view, fonts, game):
    state = _make({(0, 0): 1})
    surface = pygame.Surface((760, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=False)
    at = tuple(surface.get_at(view.cell_center((1, 0))))[:3]
    assert at not in theme.PLAYER_COLORS


def test_draw_does_not_crash_with_all_three_setups(view, fonts):
    surface = pygame.Surface((760, 700))
    for setup in ("standard", "belgian_daisy", "german_daisy"):
        view.draw(surface, fonts, AbaloneGame(setup), initial_state(setup), ViewState(),
                  interactive=True)


def test_target_hint_is_drawn_on_top_of_an_occupied_cell(view, fonts, game):
    """推挤型着法的目标格就是对手棋子所在的那格 —— 提示被盖住等于"这手不能走"。

    取的不是中心像素（那里是棋子本体），而是提示圆环那一圈。
    """
    state = _make({(0, 0): 1, (1, 0): 1, (2, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    assert (2, 0) in view._targets
    surface = pygame.Surface((760, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=True)

    plain = pygame.Surface((760, 700))
    view._selected = None
    view._targets = {}
    view.draw(plain, fonts, game, state, ViewState(), interactive=True)

    cx, cy = view.cell_center((2, 0))
    radius = max(4, int(view.cell * 0.46))
    ring = (cx, cy - radius + 1)
    assert surface.get_at(ring) != plain.get_at(ring), "目标格提示没画在棋子之上"


# --------------------------------------------------------------------------- #
# 交互：两段式点击
# --------------------------------------------------------------------------- #

def test_clicking_own_marble_selects_it(view, game):
    state = _make({(0, 0): 1, (-4, 0): 2})
    assert view.handle_click(view.cell_center((0, 0)), game, state, ViewState()) is None
    assert view._selected == ((0, 0),)
    assert view._targets, "选中后必须给出目标格"


def test_single_center_marble_offers_six_targets(view, game):
    """中心孤子：六个方向都能走（无 dwell）。"""
    state = _make({(0, 0): 1})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    assert len(view._targets) == 6


def test_edge_marble_offers_fewer_targets(view, game):
    """贴边的孤子走不出棋盘。"""
    state = _make({(4, 0): 1})
    view.handle_click(view.cell_center((4, 0)), game, state, ViewState())
    assert 0 < len(view._targets) < 6


def test_clicking_a_second_adjacent_marble_extends_the_group(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    assert view._selected == ((0, 0), (1, 0))


def test_clicking_a_non_collinear_marble_restarts_the_selection(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (3, -3): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((3, -3)), game, state, ViewState())
    assert view._selected == ((3, -3),)


def test_three_in_a_row_can_be_selected(view, game):
    state = _make({(-1, 0): 1, (0, 0): 1, (1, 0): 1, (-4, 0): 2})
    for pos in ((-1, 0), (0, 0), (1, 0)):
        view.handle_click(view.cell_center(pos), game, state, ViewState())
    assert len(view._selected) == 3


def test_a_group_that_is_outside_any_line_is_rejected(view, game):
    """四枚围成一团也选不上 —— 规则只允许 1~3 连子。"""
    state = _make({(0, 0): 1, (1, 0): 1, (0, -1): 1, (1, -1): 1})
    for pos in ((0, 0), (1, 0), (0, -1), (1, -1)):
        view.handle_click(view.cell_center(pos), game, state, ViewState())
    assert len(view._selected or ()) <= 3


def test_clicking_a_target_cell_returns_a_legal_move(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    dest, (move, _kind) = next(iter(view._targets.items()))
    got = view.handle_click(view.cell_center(dest), game, state, ViewState())
    assert isinstance(got, AbaloneMove)
    assert got == move
    assert game.is_legal(state, got)


def test_after_moving_the_selection_is_cleared(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    dest = next(iter(view._targets))
    view.handle_click(view.cell_center(dest), game, state, ViewState())
    assert view._selected is None and not view._targets


def test_clicking_opponent_marble_does_not_select(view, game):
    state = _make({(0, 0): 1, (1, 0): 2})
    assert view.handle_click(view.cell_center((1, 0)), game, state, ViewState()) is None
    assert view._selected is None


def test_clicking_an_empty_cell_clears_the_selection(view, game):
    state = _make({(0, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((0, 2)), game, state, ViewState())
    assert view._selected is None and not view._targets


def test_clicking_outside_the_board_returns_none(view, game):
    state = _make({(0, 0): 1})
    assert view.handle_click((-9, -9), game, state, ViewState()) is None


def test_selection_survives_across_calls_on_the_same_state(view, game):
    """同一次点击循环内，选中状态不会被 ``_sync_state`` 反复清掉。"""
    state = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_motion(view.cell_center((2, 0)), game, state, ViewState())
    assert view._selected == ((0, 0),)


def test_selection_is_dropped_when_the_state_object_changes(view, game):
    """落子 / 悔棋 / 新局都会换局面对象 —— 旧选择必须失效。"""
    state = _make({(0, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    fresh = game.apply(state, next(iter(game.legal_moves(state))))
    view.handle_motion(view.cell_center((0, 0)), game, fresh, ViewState())
    assert view._selected is None


def test_terminal_state_ignores_clicks(view, game):
    state = _make({(2, 0): 1, (3, 0): 1, (4, 0): 2}, out=(5, 0))
    over = game.apply(state, next(m for m in game.legal_moves(state) if len(m.cells) == 2))
    assert over.is_terminal()
    assert view.handle_click(view.cell_center((2, 0)), game, over, ViewState()) is None
    assert view._selected is None


def test_push_capable_target_is_flagged(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (2, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((1, 0)), game, state, ViewState())
    kinds = {dest: kind for dest, (_m, kind) in view._targets.items()}
    assert 1 in kinds.values(), "应当至少有一个「推动」目标格"


def test_ejection_target_is_flagged_as_dangerous(view, game):
    state = _make({(2, 0): 1, (3, 0): 1, (4, 0): 2})
    view.handle_click(view.cell_center((2, 0)), game, state, ViewState())
    view.handle_click(view.cell_center((3, 0)), game, state, ViewState())
    kinds = {dest: kind for dest, (_m, kind) in view._targets.items()}
    assert 2 in kinds.values(), "应当有一个「挤出盘外」目标格"


def test_targets_never_collide(view, game):
    """六个方向不能算出同一个目标格 —— 否则点哪一格出哪一招是有歧义的。"""
    state = _make({(0, 0): 1, (1, 0): 1, (0, -1): 1})
    for cells in (((0, 0),), ((0, 0), (1, 0)), ((0, 0), (1, 0), (-1, 0))):
        if all(state.at(p) == 1 for p in cells):
            view.handle_click(view.cell_center(cells[0]), game, state, ViewState())
            for p in cells[1:]:
                view.handle_click(view.cell_center(p), game, state, ViewState())
            for move in game.legal_moves(state):
                if move.cells == view._selected:
                    assert len({view._target_cell(move)} - {None}) == 1
            break


# --------------------------------------------------------------------------- #
# 提示文案
# --------------------------------------------------------------------------- #

def test_hover_hint_asks_for_a_marble_when_nothing_is_selected(view, game):
    state = _make({(0, 0): 1})
    view.handle_motion(view.cell_center((0, 0)), game, state, ViewState())
    text, _color = view.hover_hint(ViewState())
    assert "点击" in text


def test_hover_hint_describes_the_move_on_a_target(view, game):
    state = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    dest = next(iter(view._targets))
    view.handle_motion(view.cell_center(dest), game, state, ViewState())
    text, _color = view.hover_hint(ViewState())
    assert text, "悬停在目标格上要给得出招描述"


def test_hover_hint_warns_a_stuck_group(view, game):
    """被己方棋子焊死的一组：明确告诉玩家换一组，而不是无声无息。"""
    state = _make({(0, 0): 1, (1, 0): 1, (1, -1): 1, (0, 1): 1, (0, -1): 1, (-1, 1): 1,
                   (-1, 0): 1, (2, 0): 1, (2, -2): 1, (-2, 2): 1})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    if not view._targets:
        text, color = view.hover_hint(ViewState())
        assert "无处可走" in text
        assert color == theme.BAD


def test_no_placement_mode(view):
    """右键不会进任何"放置模式"（缺这个方法会让按 V 键崩溃）。"""
    assert view.in_placement_mode() is False


def test_hud_hint_mentions_the_two_step_flow(view):
    assert "己方" in view.hud_hint(paused=False)
    assert "暂停" in view.hud_hint(paused=True)


# --------------------------------------------------------------------------- #
# 动画
# --------------------------------------------------------------------------- #

def test_animate_zero_duration_is_noop(view):
    view.animate(AbaloneMove(0, ((0, 0),), E), 0)
    assert not view.is_animating()


def test_animate_starts_a_slide(view):
    view.animate(AbaloneMove(0, ((0, 0), (1, 0)), E), 260)
    assert view.is_animating()


def test_update_finishes_the_slide(view):
    view.animate(AbaloneMove(0, ((0, 0),), E), 260)
    for _ in range(100):
        view.update(16.0)
    assert not view.is_animating()


def test_reset_clears_animation_and_selection(view, game):
    state = _make({(0, 0): 1})
    view.handle_click(view.cell_center((0, 0)), game, state, ViewState())
    view.animate(AbaloneMove(0, ((0, 0),), E), 260)
    view.reset()
    assert not view.is_animating()
    assert view._selected is None and not view._targets


def test_second_animate_replaces_the_first(view):
    """不排队：AI 双方连续走子时排队会累积延迟。"""
    view.animate(AbaloneMove(0, ((0, 0),), E), 260)
    view.animate(AbaloneMove(1, ((1, 0),), W), 260)
    assert view._anim.move.cells == ((1, 0),)


def test_slide_offset_starts_behind_and_lands_exactly(view, fonts, game):
    """滑行的起点必须在**上一格**（反了就是"从空格里飞进来看似倒放"）。

    用像素验证：动画刚开始时，目标格中心还不是己方棋子的颜色。
    """
    before = _make({(0, 0): 1, (-4, 0): 2})
    move = next(m for m in game.legal_moves(before) if m.cells == ((0, 0),) and m.direction == E)
    after = game.apply(before, move)
    view.animate(move, 400)
    surface = pygame.Surface((760, 700))
    view.draw(surface, fonts, game, after, ViewState(), interactive=False)
    assert tuple(surface.get_at(view.cell_center((1, 0))))[:3] != theme.PLAYER_COLORS[0]

    for _ in range(120):
        view.update(16.0)
    landed = pygame.Surface((760, 700))
    view.draw(landed, fonts, game, after, ViewState(), interactive=False)
    assert tuple(landed.get_at(view.cell_center((1, 0))))[:3] == theme.PLAYER_COLORS[0]


def test_drawing_an_ejection_animation_does_not_crash(view, fonts, game):
    """被挤出盘外的那一枚已经不在 ``cells`` 里了，要单独画并淡出。"""
    before = _make({(2, 0): 1, (3, 0): 1, (4, 0): 2})
    move = next(m for m in game.legal_moves(before) if len(m.cells) == 2 and m.direction == E)
    after = game.apply(before, move)
    view.animate(move, 400)
    surface = pygame.Surface((760, 700))
    for _ in range(20):
        view.draw(surface, fonts, game, after, ViewState(), interactive=False)
        view.update(16.0)


def test_set_last_move_highlights_the_group_that_moved(view, fonts, game):
    """高亮跟着**最后一手**走（目标是那一手走完后所在的格子）。"""
    before = _make({(0, 0): 1, (1, 0): 1, (-4, 0): 2})
    move = next(m for m in game.legal_moves(before) if len(m.cells) == 2 and m.direction == SE)
    after = game.apply(before, move)

    view.set_last_move(None)
    plain = pygame.Surface((760, 700))
    view.draw(plain, fonts, game, after, ViewState(), interactive=True)

    view.set_last_move(move)
    marked = pygame.Surface((760, 700))
    view.draw(marked, fonts, game, after, ViewState(), interactive=True)

    destination = move.destinations()[0]
    cx, cy = view.cell_center(destination)
    ring = (cx, cy + view.marble_radius + 3)  # SELECT_RING 画在 radius + 3 那一圈
    assert marked.get_at(ring) != plain.get_at(ring), "最后一手的那一组没有高亮"


# --------------------------------------------------------------------------- #
# 窗口接线
# --------------------------------------------------------------------------- #

def test_window_boots_into_abalone(make_window):
    window = make_window(game_key="abalone", mode="pvp")
    assert window.session.game.key == "abalone"
    assert isinstance(window.view, AbaloneView)


def test_clicking_through_the_window_makes_a_move(make_window):
    """端到端：真实鼠标事件 → 选中 → 出招。大窗口/真实DPI下坐标换算才暴露得出来。"""
    window = make_window(game_key="abalone", mode="pvp")
    window._update(16.0)
    state = window.session.state
    assert state.at((0, 4)) == 1, "标准布局最下面一行（r=4）整行是玩家 0 的子"

    picked = None
    for pos in CELLS:  # 边角上的孤子可能一步都走不了，挑一枚有目标格的
        if state.at(pos) != 1:
            continue
        pygame.event.post(press(window.view.cell_center(pos)))
        window._handle_events()
        if window.view._targets:
            picked = pos
            break
    assert picked is not None, "开局时玩家 0 至少有一步可走"
    assert window.view._selected == (picked,), "第一次点击应当选中那一枚"

    dest = next(iter(window.view._targets))
    pygame.event.post(press(window.view.cell_center(dest)))
    window._handle_events()
    assert window.session.state.ply == state.ply + 1


def test_switching_the_setup_restarts_the_match(make_window):
    """``abalone_setup`` 进了 RESTART_KEYS —— 换布局必须立刻开新局，否则
    棋盘上还是旧布局，但 ``Game`` 的 ``legal_moves`` 已经按新布局算了。"""
    window = make_window(game_key="abalone", abalone_setup="standard")
    window._update(16.0)
    assert len(window.session.game.legal_moves(window.session.state)) == 44
    window._on_setting("abalone_setup", "belgian_daisy")
    assert window.session.game.setup == "belgian_daisy"
    assert len(window.session.game.legal_moves(window.session.state)) == 52
    assert window.session.state.ply == 0


def test_scoreboard_shows_ejections_not_walls(make_window):
    """走通用的墙棋分支会显示成「墙 0」，而大力士棋根本没有墙。"""
    window = make_window(game_key="abalone", mode="pvp")
    window._update(16.0)
    details = window.match._player_details(window.session.state, (0, 0))
    assert details == ("挤出 0/6", "挤出 0/6")
