"""游戏选择大厅：渲染、导航、场景切换。

这些用例也顺带守着两条"新增游戏时容易漏"的约定：

* 侧栏参数按**游戏**过滤 —— 四子棋不该看到"每人墙数"，墙棋不该看到"列数"；
* 侧栏标题跟随当前棋类 —— 不该永远写死"步步为营"。
"""

from __future__ import annotations

import pygame
from helpers import key_event, press, release

from boardgames.ui import theme
from boardgames.ui.lobby import ICON_H
from boardgames.ui.rules_panel import rules_sections


def _lobby_window(make_window, **overrides):
    window = make_window(start_scene="lobby", **overrides)
    window._update(16.0)
    return window


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #

def test_lobby_renders_without_error(make_window):
    window = _lobby_window(make_window)
    window.run(max_frames=3)


def test_lobby_has_one_card_per_registered_game(make_window):
    window = _lobby_window(make_window)
    keys = [card.game.key for card in window.lobby._cards]
    assert keys == window.registry.keys()
    assert "quoridor" in keys
    assert "connect4" in keys


def test_cards_have_readable_metadata(make_window):
    window = _lobby_window(make_window)
    for card in window.lobby._cards:
        assert card.game.display_name
        assert card.game.tagline
        assert card.game.summary
        assert card.game.rules, f"{card.game.key} 应当有玩法要点"


def test_cards_are_laid_out_inside_the_window(make_window):
    window = _lobby_window(make_window)
    area = window.screen.get_rect()
    for card in window.lobby._cards:
        assert card.rect.width > 0 and card.rect.height > 0
        assert area.left <= card.rect.left
        assert area.right >= card.rect.right


def test_small_window_keeps_cards_usable(make_window):
    """小窗口下卡片必须完整可见（不能画到屏幕外）。"""
    for size in ((760, 560), (800, 600), (900, 640)):
        window = make_window(start_scene="lobby")
        window.screen = pygame.display.set_mode(size)
        window._layout()
        area = window.screen.get_rect()
        for card in window.lobby._cards:
            assert card.rect.width > 0 and card.rect.height > 0
            assert area.left <= card.rect.left, f"{size} 下卡片左边越界"
            assert area.right >= card.rect.right, f"{size} 下卡片右边越界"


def test_tiny_window_enables_scroll(make_window):
    """极小窗口下单列放不下，必须能滚，否则底部一排会画到屏幕外。"""
    window = make_window(start_scene="lobby")
    window.screen = pygame.display.set_mode((480, 420))
    window._layout()
    assert window.lobby.max_scroll > 0, "极小窗口下应当可滚动"

    window.lobby._scroll_by(400)
    assert window.lobby.scroll > 0
    window.lobby._scroll_by(-10000)
    assert window.lobby.scroll == 0.0, "滚动量必须夹在合法范围内"


def test_scroll_is_clamped(make_window):
    window = make_window(start_scene="lobby")
    window.screen = pygame.display.set_mode((480, 420))
    window._layout()
    window.lobby._scroll_by(100000)
    assert window.lobby.scroll == window.lobby.max_scroll


def test_large_window_fits_without_scroll(make_window):
    window = make_window(start_scene="lobby")
    window.screen = pygame.display.set_mode((1400, 900))
    window._layout()
    assert window.lobby.max_scroll == 0.0


# --------------------------------------------------------------------------- #
# 交互
# --------------------------------------------------------------------------- #

def test_hover_marks_a_card(make_window):
    window = _lobby_window(make_window)
    card = window.lobby._cards[0]
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": card.rect.center, "rel": (0, 0), "buttons": (0, 0, 0)}
    ))
    window._handle_events()
    assert window.lobby._hover == 0
    assert window.lobby._focus == 0


def test_click_card_enters_match(make_window):
    window = _lobby_window(make_window)
    card = next(c for c in window.lobby._cards if c.game.key == "connect4")
    pygame.event.post(press(card.rect.center))
    window._handle_events()

    assert window.scene is window.match
    assert window.game_key == "connect4"
    assert window.session.game.key == "connect4"


def test_click_quoridor_card_switches_game(make_window, ):
    window = _lobby_window(make_window)
    window.goto_match("connect4")
    window.goto_lobby()
    card = next(c for c in window.lobby._cards if c.game.key == "quoridor")
    pygame.event.post(press(card.rect.center))
    window._handle_events()

    assert window.scene is window.match
    assert window.game_key == "quoridor"
    assert window.session.game.display_name == "步步为营"


def test_click_empty_area_does_nothing(make_window):
    window = _lobby_window(make_window)
    pygame.event.post(press((4, 4)))
    window._handle_events()
    assert window.scene is window.lobby


def test_keyboard_navigation_moves_focus(make_window):
    window = _lobby_window(make_window)
    count = len(window.lobby._cards)
    assert count >= 2

    pygame.event.post(key_event(pygame.K_RIGHT))
    window._handle_events()
    assert window.lobby._focus == 1

    pygame.event.post(key_event(pygame.K_LEFT))
    window._handle_events()
    assert window.lobby._focus == 0

    # 从第一项再往左会绕回最后一项
    pygame.event.post(key_event(pygame.K_LEFT))
    window._handle_events()
    assert window.lobby._focus == count - 1


def test_enter_opens_focused_card(make_window):
    window = _lobby_window(make_window)
    window.lobby._focus = 0
    window.lobby._hover = 0
    pygame.event.post(key_event(pygame.K_RETURN))
    window._handle_events()
    assert window.scene is window.match
    assert window.game_key == window.lobby._cards[0].game.key


def test_escape_in_lobby_quits(make_window):
    window = _lobby_window(make_window)
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is False


# --------------------------------------------------------------------------- #
# 场景切换
# --------------------------------------------------------------------------- #

def test_lobby_button_returns_to_lobby(make_window):
    """侧栏底栏的「大厅」按钮。"""
    window = make_window(mode="pvp")
    assert window.scene is window.match
    window._on_action("lobby", None)
    assert window.scene is window.lobby


def test_lobby_button_is_in_the_footer(make_window):
    window = make_window(mode="pvp")
    window._update(16.0)
    labels = [b.label for b in window.sidebar._visible_footer()]
    assert "大厅" in labels
    assert "大厅" in [b.label for b in window.sidebar.footer_buttons]


def test_escape_from_match_goes_to_lobby(make_window):
    window = make_window(mode="pvp")
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.scene is window.lobby
    assert window.running is True


def test_escape_three_levels(make_window):
    """对局 → 大厅 → 退出。"""
    window = make_window(mode="pvp")

    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.scene is window.lobby, "第 1 次 Esc 回大厅"

    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert window.running is False, "第 2 次 Esc 退出程序"


def test_caption_follows_scene(make_window):
    window = _lobby_window(make_window)
    assert "选棋" in pygame.display.get_caption()[0]
    window.goto_match("connect4")
    assert "重力四子棋" in pygame.display.get_caption()[0]
    window.goto_lobby()
    assert "选棋" in pygame.display.get_caption()[0]


def test_returning_to_lobby_keeps_match_state(make_window):
    """回大厅再进来，之前那局还在（不该被清空）。"""
    window = make_window(mode="pvp")
    pos = window.view.cell_center(*window.session.game.pawn_moves_for(window.session.state, 0)[0].dst)
    pygame.event.post(press(pos))
    window._handle_events()
    assert len(window.session.history) == 2

    window.goto_lobby()
    window.goto_match()
    assert len(window.session.history) == 2, "同一棋类不该重开新局"


def test_switching_game_starts_a_new_session(make_window):
    window = make_window(mode="pvp")
    window.goto_match("connect4")
    assert window.session.game.key == "connect4"
    assert len(window.session.history) == 1


def test_leaving_match_stops_ai_thinking(make_window):
    """回大厅必须停掉后台 AI 线程，否则它会继续跑并持有旧局面的引用。

    ``worker.cancel()`` 只是打标记，线程真正退出要等它跑到检查点，
    所以这里轮询等待而不是断言瞬间为 False。
    """
    import time

    window = make_window(
        mode="eve", p1_type="minimax", p2_type="minimax",
        minimax_depth=4, minimax_time_ms=1500, ai_delay_ms=0, anim_ms=0,
    )
    window.session.paused = False
    window.session.start_thinking()
    assert window.session.is_thinking()

    window.goto_lobby()
    # 逻辑状态立刻复位
    assert not window.session._pending_move
    # 线程在有限时间内退出
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and window.session.worker.is_running():
        time.sleep(0.01)
    assert not window.session.worker.is_running(), "回大厅后 AI 线程没有停下来"


# --------------------------------------------------------------------------- #
# 侧栏随棋类变化
# --------------------------------------------------------------------------- #

def test_sidebar_title_follows_game(make_window):
    window = make_window(mode="pvp", game_key="connect4")
    assert window.sidebar.game_title == "重力四子棋"
    assert window.sidebar.game_key == "connect4"


def test_sidebar_hides_quoridor_only_params_for_connect4(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax", game_key="connect4")
    window._update(16.0)
    keys = {w.key for s in window.sidebar._active_sections() for w in sidebar_widgets(window, s)}
    assert "connect4_cols" in keys and "connect4_rows" in keys
    assert "board_size" not in keys, "四子棋不该看到「棋盘尺寸」"
    assert "walls_per_player" not in keys, "四子棋不该看到「每人墙数」"
    assert "show_wall_slots" not in keys


def test_sidebar_hides_connect4_only_params_for_quoridor(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax")
    window._update(16.0)
    keys = {w.key for s in window.sidebar._active_sections() for w in sidebar_widgets(window, s)}
    assert "board_size" in keys and "walls_per_player" in keys
    assert "connect4_cols" not in keys, "墙棋不该看到「列数」"
    assert "connect4_rows" not in keys
    assert "c4_anim_ms" not in keys


def test_sidebar_shows_connect4_eval_weights(make_window):
    window = make_window(mode="pve", p1_type="human", p2_type="minimax", game_key="connect4")
    window._update(16.0)
    keys = {w.key for s in window.sidebar._active_sections() for w in sidebar_widgets(window, s)}
    assert {"w_material", "w_center", "w_line", "w_threat"} <= keys
    assert "w_path" not in keys, "四子棋不该看到墙棋的「最短路径差」"
    assert "w_tempo" not in keys, "四子棋没有节奏项（会破坏评估对称性）"


def sidebar_widgets(window, section):
    return window.sidebar._section_widgets(section)


# --------------------------------------------------------------------------- #
# 卡片图标：一局棋里的一个瞬间
# --------------------------------------------------------------------------- #

def _icon_surface(window, kind: str, pad: int = 48):
    """把某个图标单独画在一块留了边距的表面上，便于做像素级断言。"""
    width = 240
    surface = pygame.Surface((width, ICON_H + pad * 2))
    surface.fill((0, 0, 0))
    rect = pygame.Rect(0, pad, width, ICON_H)
    window.lobby._draw_icon(surface, rect, kind)
    return surface, rect


def _blobs(surface: pygame.Surface, colors) -> int:
    """数出某种颜色的独立色块个数 —— 图标里的"棋子"就是这种块。"""
    wanted = {tuple(color[:3]) for color in colors}
    width, height = surface.get_size()
    mask = [
        [tuple(surface.get_at((x, y)))[:3] in wanted for x in range(width)]
        for y in range(height)
    ]
    seen = [[False] * width for _ in range(height)]
    count = 0
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            count += 1
            seen[y][x] = True
            stack = [(x, y)]
            while stack:
                cx, cy = stack.pop()
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
    return count


def test_connect4_icon_keeps_every_piece_on_the_board(make_window):
    """落点用"格子里的虚线预览"表示，不许再悬一枚子在线盘上方。"""
    window = _lobby_window(make_window)
    surface, rect = _icon_surface(window, "drop")
    player_colors = (*theme.PLAYER_COLORS, *theme.PLAYER_DARK)
    above = surface.subsurface(pygame.Rect(0, 0, surface.get_width(), rect.top))
    assert _blobs(above, player_colors) == 0, "四子棋图标上方不该有棋子"
    assert _blobs(surface.subsurface(rect), theme.PLAYER_COLORS) >= 5, "棋盘上应当有棋子"


def test_abalone_icon_shows_a_crowd_of_marbles(make_window):
    """残局的样子：盘上双方都还剩一批子，不是光秃秃四个。"""
    window = _lobby_window(make_window)
    surface, rect = _icon_surface(window, "hex")
    board = surface.subsurface(rect)
    own = _blobs(board, [theme.PLAYER_COLORS[0]])
    rival = _blobs(board, [theme.PLAYER_COLORS[1]])
    assert own >= 5, f"己方只画了 {own} 枚，太少了"
    assert rival >= 3, f"对方只画了 {rival} 枚，太少了"


def test_every_icon_draws_something(make_window):
    window = _lobby_window(make_window)
    for kind in ("board", "drop", "hex", "hive", "dots"):
        surface, rect = _icon_surface(window, kind)
        board = surface.subsurface(rect)
        painted = [
            board.get_at((x, y))[:3]
            for y in range(0, rect.height, 3)
            for x in range(0, rect.width, 3)
        ]
        assert any(color != (0, 0, 0) for color in painted), f"{kind} 图标什么都没画"


# --------------------------------------------------------------------------- #
# 卡片上的「规则说明」按钮
# --------------------------------------------------------------------------- #

def test_every_card_has_a_rules_button_in_its_lower_half(make_window):
    window = _lobby_window(make_window)
    for card in window.lobby._cards:
        assert card.rect.contains(card.rules_rect), f"{card.game.key} 的规则按钮跑出卡片了"
        assert card.rules_rect.top > card.rect.centery, f"{card.game.key} 的规则按钮不在下半部"


def test_clicking_the_rules_button_opens_the_panel_without_entering(make_window):
    window = _lobby_window(make_window)
    card = window.lobby._cards[2]
    pygame.event.post(press(card.rules_rect.center))
    pygame.event.post(release(card.rules_rect.center))
    window._handle_events()

    assert window.scene is window.lobby, "点「规则说明」不该直接进对局"
    assert window.lobby.rules.open
    assert window.lobby.rules.game.key == card.game.key


def test_rules_panel_is_modal_while_open(make_window):
    window = _lobby_window(make_window)
    window.lobby._open_rules(0)
    other = window.lobby._cards[3]
    pygame.event.post(press(other.rect.center))
    window._handle_events()

    assert window.scene is window.lobby
    assert window.lobby.rules.open, "浮层开着时点卡片不该关掉它，也不该进对局"


def test_rules_panel_closes_on_escape(make_window):
    window = _lobby_window(make_window)
    window.lobby._open_rules(1)
    pygame.event.post(key_event(pygame.K_ESCAPE))
    window._handle_events()
    assert not window.lobby.rules.open
    assert window.running is True, "Esc 关浮层不该顺手把程序也退了"


def test_rules_panel_closes_on_clicking_the_veil(make_window):
    window = _lobby_window(make_window)
    window.lobby._open_rules(1)
    pygame.event.post(press((6, 6)))
    window._handle_events()
    assert not window.lobby.rules.open


def test_r_key_opens_the_rules_of_the_focused_card(make_window):
    window = _lobby_window(make_window)
    window.lobby._focus = 2
    pygame.event.post(key_event(pygame.K_r))
    window._handle_events()
    assert window.lobby.rules.open
    assert window.lobby.rules.game.key == window.lobby._cards[2].game.key


def test_every_game_has_a_readable_rulebook(make_window):
    """规则说明的正文来自 Game 的元数据 —— 四个棋类都得写全。"""
    window = _lobby_window(make_window)
    for card in window.lobby._cards:
        titles = [title for title, _ in rules_sections(card.game)]
        assert "目标" in titles, f"{card.game.key} 没写 goal"
        assert "规则" in titles, f"{card.game.key} 没写 rules"
        assert "操作" in titles, f"{card.game.key} 没写 howto"
        assert len(card.game.rules) >= 4, f"{card.game.key} 的规则条目太少"
