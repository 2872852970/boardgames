"""四子棋棋盘视图：点击投子、悬停预览、落子动画偏移。"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from boardgames.games.connect4.move import DropMove
from boardgames.games.connect4.rules import Connect4Game
from boardgames.games.connect4.state import Connect4State
from boardgames.games.connect4.view import Connect4View
from boardgames.ui import theme
from boardgames.ui.board_view import ViewState
from boardgames.ui.fonts import FontBook


def _state(cols: int = 7, rows: int = 6, current: int = 0) -> Connect4State:
    return Connect4State(
        cols=cols, rows=rows, cells=(0,) * (cols * rows), heights=(0,) * cols,
        current=current, ply=0, winner_player=None,
    )


def _with_pieces(cols: int, rows: int, pieces: dict[tuple[int, int], int], current: int = 0):
    cells = [0] * (cols * rows)
    for (c, r), v in pieces.items():
        cells[r * cols + c] = v
    heights = []
    for c in range(cols):
        h = 0
        for r in range(rows):
            if cells[r * cols + c]:
                h = r + 1
        heights.append(h)
    return Connect4State(
        cols=cols, rows=rows, cells=tuple(cells), heights=tuple(heights),
        current=current, ply=sum(1 for v in cells if v), winner_player=None,
    )


@pytest.fixture
def view():
    v = Connect4View()
    v.layout(pygame.Rect(0, 0, 800, 700))
    return v


@pytest.fixture
def game():
    return Connect4Game()


@pytest.fixture
def fonts():
    return FontBook()


# --------------------------------------------------------------------------- #
# 布局
# --------------------------------------------------------------------------- #

def test_layout_produces_positive_cell(view):
    assert view.cell >= 16
    assert len(view.origin) == 2


def test_cell_center_inside_board(view):
    center = view.cell_center(0, 0)
    board = view.board_rect()
    assert board.collidepoint(center)


def test_set_size_relayouts(view):
    view.set_size(8, 5)
    assert view.cols == 8 and view.rows == 5


# --------------------------------------------------------------------------- #
# 重力方向（局面 row 0 = 最底行，屏幕上必须画在棋盘下部）
# --------------------------------------------------------------------------- #

def test_row_zero_is_at_the_bottom_of_the_board(view):
    board = view.board_rect()
    y_bottom = view.cell_center(0, 0)[1]
    y_top = view.cell_center(0, view.rows - 1)[1]
    assert y_bottom > y_top
    assert board.bottom - view.cell <= y_bottom <= board.bottom
    assert board.top <= y_top <= board.top + view.cell


def test_gravity_paints_pieces_at_the_bottom(view, fonts, game):
    """落一枚在第 3 列，像素上必须出现在棋盘**底部**那格（曾经堆在顶部）。"""
    state = _with_pieces(7, 6, {(2, 0): 1})
    surface = pygame.Surface((800, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=False)
    assert tuple(surface.get_at(view.cell_center(2, 0)))[:3] == theme.PLAYER_COLORS[0]
    assert tuple(surface.get_at(view.cell_center(2, view.rows - 1)))[:3] != theme.PLAYER_COLORS[0]


def test_stacking_paints_upward(view, fonts, game):
    """同一列叠两枚：第二枚在**上面**那格。"""
    state = _with_pieces(7, 6, {(2, 0): 1, (2, 1): 2})
    surface = pygame.Surface((800, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=False)
    assert tuple(surface.get_at(view.cell_center(2, 0)))[:3] == theme.PLAYER_COLORS[0]
    assert tuple(surface.get_at(view.cell_center(2, 1)))[:3] == theme.PLAYER_COLORS[1]


def test_col_at_maps_x_to_column(view):
    """整列都是合法点击区，不必精确对准圆窝。"""
    for col in range(view.cols):
        x = view.origin[0] + col * view.cell + view.cell // 2
        assert view.col_at((x, 300)) == col


def test_col_at_outside_returns_none(view):
    assert view.col_at((-10, 300)) is None
    assert view.col_at((view.board_rect().right + 50, 300)) is None


# --------------------------------------------------------------------------- #
# 交互：点击投子
# --------------------------------------------------------------------------- #

def test_click_returns_drop_move_on_bottom_row(view, game):
    state = _state()
    pos = view.cell_center(3, 0)
    move = view.handle_click(pos, game, state, ViewState())
    assert isinstance(move, DropMove)
    assert move.col == 3
    assert move.row == 0
    assert move.player == 0


def test_click_stacks_on_existing_piece(view, game):
    """第 3 列已有一枚，投子应落在 row 1。"""
    state = _with_pieces(7, 6, {(3, 0): 1}, current=1)
    move = view.handle_click(view.cell_center(3, 0), game, state, ViewState())
    assert move.row == 1
    assert move.player == 1


def test_click_full_column_returns_none(view, game):
    """列已满 → 无处可投。"""
    pieces = {(2, r): 1 for r in range(6)}
    state = _with_pieces(7, 6, pieces)
    assert view.handle_click(view.cell_center(2, 5), game, state, ViewState()) is None


def test_click_outside_board_returns_none(view, game):
    state = _state()
    assert view.handle_click((-5, -5), game, state, ViewState()) is None


def test_click_on_terminal_returns_none(view, game):
    pieces = {(c, 0): 1 for c in range(4)}
    state = _with_pieces(7, 6, pieces)
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 4))
    assert won.is_terminal()
    assert view.handle_click(view.cell_center(0, 5), game, won, ViewState()) is None


# --------------------------------------------------------------------------- #
# 悬停预览
# --------------------------------------------------------------------------- #

def test_hover_marks_open_column(view, game):
    state = _state()
    view.handle_motion(view.cell_center(2, 0), game, state, ViewState())
    assert view._hover_col == 2


def test_hover_ignored_when_outside(view, game):
    state = _state()
    view.handle_motion((-5, -5), game, state, ViewState())
    assert view._hover_col is None


def test_hover_ignored_when_terminal(view, game):
    pieces = {(c, 0): 1 for c in range(4)}
    state = _with_pieces(7, 6, pieces)
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 4))
    view.handle_motion(view.cell_center(2, 0), game, won, ViewState())
    assert view._hover_col is None


def test_hover_hint_mentions_column(view, game):
    state = _state()
    view.handle_motion(view.cell_center(4, 0), game, state, ViewState())
    text, _ = view.hover_hint(ViewState())
    assert "5" in text or "第" in text


# --------------------------------------------------------------------------- #
# 落子预览：必须严丝合缝地落在槽位里，且是当前行棋方的颜色
# --------------------------------------------------------------------------- #

def test_ghost_centre_is_the_socket_centre(view, game):
    state = _state()
    view.handle_motion(view.cell_center(2, 0), game, state, ViewState())
    assert view.ghost_center(state) == view.cell_center(2, state.heights[2])


def test_ghost_stacks_on_existing_pieces(view, game):
    """第 3 列已有一枚 → 预览落在 row 1 的槽位里。"""
    state = _with_pieces(7, 6, {(2, 0): 1})
    view.handle_motion(view.cell_center(2, 0), game, state, ViewState())
    assert view.ghost_center(state) == view.cell_center(2, 1)


def test_ghost_fits_the_socket_exactly(view, fonts, game):
    """预览棋子不得越出槽位圆 —— 曾经整体上移 0.12 格，看着就是"没对准"。"""
    state = _state()
    view.handle_motion(view.cell_center(2, 0), game, state, ViewState())
    hovered = pygame.Surface((800, 700))
    view.draw(hovered, fonts, game, state, ViewState(), interactive=True)

    view._hover_col = None
    plain = pygame.Surface((800, 700))
    view.draw(plain, fonts, game, state, ViewState(), interactive=False)

    cx, cy = view.cell_center(2, 0)
    radius = view.socket_radius
    assert hovered.get_at((cx, cy)) != plain.get_at((cx, cy)), "悬停应当画出预览棋子"
    for dx, dy in ((radius + 2, 0), (-(radius + 2), 0), (0, radius + 2), (0, -(radius + 2))):
        assert hovered.get_at((cx + dx, cy + dy)) == plain.get_at((cx + dx, cy + dy)), (
            f"预览跑出槽位: {(dx, dy)}"
        )


@pytest.mark.parametrize(
    ("current", "want_red_more"),
    [(0, True), (1, False)],
)
def test_ghost_uses_the_current_players_colour(view, fonts, game, current, want_red_more):
    """预览颜色跟着**行棋方**走（索引 0/1，不是棋子值 1/2 —— 后者会越界）。"""
    state = _state(current=current)
    view.handle_motion(view.cell_center(3, 0), game, state, ViewState())
    surface = pygame.Surface((800, 700))
    view.draw(surface, fonts, game, state, ViewState(), interactive=True)
    pixel = surface.get_at(view.cell_center(3, 0))
    assert (pixel[0] > pixel[2]) is want_red_more, f"颜色不对: {tuple(pixel)}"


# --------------------------------------------------------------------------- #
# 动画
# --------------------------------------------------------------------------- #

def test_animate_zero_duration_is_noop(view):
    view.animate(DropMove(col=0, row=0, player=0), 0)
    assert not view.is_animating()


def test_animate_starts_bounce(view):
    view.animate(DropMove(col=2, row=0, player=0), 850)
    assert view.is_animating()


def test_update_finishes_bounce(view):
    view.animate(DropMove(col=2, row=0, player=0), 300)
    for _ in range(200):
        view.update(16.0)
    assert not view.is_animating()


def test_reset_clears_animation(view):
    view.animate(DropMove(col=2, row=0, player=0), 850)
    view.reset()
    assert not view.is_animating()


def test_second_animate_replaces_first(view):
    """不排队：AI 连续落子时不累积延迟。"""
    view.animate(DropMove(col=0, row=0, player=0), 850)
    view.animate(DropMove(col=1, row=0, player=1), 850)
    assert view._anim.move.col == 1


def test_bounce_starts_above_and_finishes_in_slot(view):
    """动画：起点在槽位**上方**，播完停在槽位里（不能是反的）。"""
    view.animate(DropMove(col=0, row=0, player=0), 850)
    tween = view._anim.tween
    assert tween.offset() == -tween.drop_px
    for _ in range(200):
        view.update(16.0)
    assert not view.is_animating()


def test_drop_distance_grows_with_depth(view):
    """落点越低，从棋盘上沿掉下来的落差越大；两者的起点都在上沿之上。"""
    view.animate(DropMove(col=0, row=0, player=0), 850)
    deep = view.drop_px_for(0)
    shallow = view.drop_px_for(view.rows - 1)
    assert deep > shallow
    top = view.board_rect().top
    assert view.cell_center(0, 0)[1] - deep < top
    assert view.cell_center(0, view.rows - 1)[1] - shallow < top


def test_no_placement_mode(view):
    assert view.in_placement_mode() is False


def test_hud_hint_mentions_column(view):
    hint = view.hud_hint(paused=False)
    assert "列" in hint


def test_hud_hint_paused(view):
    assert "暂停" in view.hud_hint(paused=True)


# --------------------------------------------------------------------------- #
# 绘制
# --------------------------------------------------------------------------- #

def test_draw_does_not_crash(view, fonts, game):
    surface = pygame.Surface((800, 700))
    view.draw(surface, fonts, game, _state(), ViewState(), interactive=True)


def test_draw_with_pieces_does_not_crash(view, fonts, game):
    surface = pygame.Surface((800, 700))
    state = _with_pieces(7, 6, {(0, 0): 1, (1, 0): 2, (1, 1): 1})
    view.draw(surface, fonts, game, state, ViewState(), interactive=True)


def test_draw_won_state_does_not_crash(view, fonts, game):
    surface = pygame.Surface((800, 700))
    pieces = {(c, 0): 1 for c in (0, 1, 2)}
    state = _with_pieces(7, 6, pieces)
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 3))
    view.draw(surface, fonts, game, won, ViewState(), interactive=False)
    assert view._win_line is not None


def test_win_highlight_works_for_player_2(view, fonts, game):
    """玩家 2（索引 1）赢棋时的高亮；把索引当棋子值用会 IndexError。"""
    surface = pygame.Surface((800, 700))
    pieces = {(c, 0): 2 for c in (0, 1, 2)}
    state = _with_pieces(7, 6, pieces, current=1)
    won = game.apply(state, next(m for m in game.legal_moves(state) if m.col == 3))
    assert won.winner_player == 1
    view.draw(surface, fonts, game, won, ViewState(), interactive=False)
    assert view._win_line is not None
    assert all(won.at(col, row) == 2 for col, row in view._win_line)


def test_draw_updates_size_from_state(view, fonts, game):
    surface = pygame.Surface((800, 700))
    state = _state(cols=8, rows=5)
    view.draw(surface, fonts, game, state, ViewState(), interactive=True)
    assert view.cols == 8 and view.rows == 5
