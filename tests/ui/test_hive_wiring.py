"""昆虫棋的"接线"：参数表 / 侧栏 / 场景文案 / 大厅图标。

内核与视图各自有测试，这里只守**把它们接起来**的那几处 —— 都是"改了之后
界面上看不出任何变化"的静默失效：

* 侧栏参数没标 ``games=("hive",)`` → 开关压根不出现；
* 权重没进 ``WEIGHT_KEYS`` → 滑块拖到底评估函数一动不动；
* 开关没进 ``RESTART_KEYS`` → 切了扩展虫但用的还是旧局面。
"""

from __future__ import annotations

import pygame

from boardgames.games.hive.heuristic import merged_weights
from boardgames.settings.schema import SPEC_BY_KEY, WEIGHT_KEYS
from boardgames.ui.match_scene import RESTART_KEYS

HIVE_WEIGHTS = ("w_hive_surround", "w_hive_buried", "w_hive_queen",
                "w_hive_mobility", "w_hive_hand", "w_hive_contact", "p_hive_place")


# --------------------------------------------------------------------------- #
# 参数表
# --------------------------------------------------------------------------- #

def test_hive_expansion_is_declared_and_scoped_to_hive():
    spec = SPEC_BY_KEY["hive_expansion"]
    assert spec.kind == "bool"
    assert spec.default is False
    assert spec.games == ("hive",), "不标 games 会在别的棋类侧栏里冒出来"


def test_hive_expansion_restarts_the_game():
    assert "hive_expansion" in RESTART_KEYS, "切扩展虫不开新局 → 手牌配额还是旧的"


def test_hive_weights_are_wired_into_the_weight_channel():
    """``Settings.weights()`` 只搬运 ``WEIGHT_KEYS`` 里的键。"""
    for key in HIVE_WEIGHTS:
        assert key in WEIGHT_KEYS, f"{key} 没进 WEIGHT_KEYS，滑块改了完全无效"
        assert key in SPEC_BY_KEY


def test_hive_weights_reach_the_evaluator(make_window):
    """端到端：滑块的值真的进了评估函数（不是只在 JSON 里躺着）。"""
    window = make_window(game_key="hive", w_hive_surround=7.0)
    merged = merged_weights(window.settings.weights())
    assert merged["w_hive_surround"] == 7.0
    # 别的棋类的键必须被丢掉（否则改墙棋权重会连带改昆虫棋的评估）
    assert "w_path" not in merged
    # 自己没动的键仍是默认值
    assert merged["w_hive_buried"] == 40.0


# --------------------------------------------------------------------------- #
# 侧栏
# --------------------------------------------------------------------------- #

def _match_window(make_window, **overrides):
    window = make_window(game_key="hive", **overrides)
    window._update(16.0)
    return window


def _applicable_keys(sidebar) -> set[str]:
    """侧栏**当前真的会画出来**的参数键。

    控件是一开始就全部建好的，过滤发生在绘制 / 事件派发时
    （``_section_widgets``），所以不能只查控件在不在。
    """
    return {widget.key
            for section in sidebar._active_sections()
            for widget in sidebar._section_widgets(section)}


def _panel_keys(window) -> set[str]:
    """「设置」浮层里当前会画出来的参数键（评估权重 / 界面与操作都在这）。"""
    window.settings_panel.show(window.match.game_key, window.session.resolved_player_types())
    return {widget.key for widget in window.settings_panel._visible_widgets()}


def test_sidebar_shows_hive_only_params(make_window):
    window = _match_window(make_window)
    keys = _applicable_keys(window.sidebar)
    assert "hive_expansion" in keys, "扩展虫开关该出现"
    assert "first_player" in keys


def test_settings_panel_shows_hive_weights_and_ui_params(make_window):
    window = _match_window(make_window)
    keys = _panel_keys(window)
    assert "w_hive_surround" in keys, "昆虫棋的评估权重该出现在「设置」里"
    assert "hive_anim_ms" in keys, "界面与操作也该在「设置」里"


def test_sidebar_hides_other_games_params(make_window):
    window = _match_window(make_window)
    for key in ("board_size", "walls_per_player", "connect4_cols", "abalone_setup"):
        assert key not in _applicable_keys(window.sidebar), f"昆虫棋不该看到 {key}"
    # 别的棋类的权重 / 动画参数也不能通过「设置」溜进来
    panel = _panel_keys(window)
    for key in ("w_path", "w_material", "w_abalone_out", "c4_anim_ms"):
        assert key not in panel, f"昆虫棋不该看到 {key}"


def test_toggling_expansion_restarts_with_new_pieces(make_window):
    window = _match_window(make_window)
    session = window.match.session
    assert session.state.expansion is False

    window.match._on_setting("hive_expansion", True)
    state = window.match.session.state
    assert state.expansion is True
    assert state.ply == 0 and not state.stacks, "切换后必须是全新一局"
    # 扩展虫各一枚都该在手牌里
    for kind in ("ladybug", "mosquito", "pillbug"):
        assert state.hand_left(0, kind) == 1, f"{kind} 没进手牌配额"


# --------------------------------------------------------------------------- #
# 场景文案 / 动画时长
# --------------------------------------------------------------------------- #

def test_player_details_show_the_victory_progress(make_window):
    window = _match_window(make_window)
    status = window.match._build_status()
    for detail in status.player_details:
        assert "围" in detail and "手牌" in detail, detail
    assert "墙" not in status.player_details[0], "昆虫棋没有墙"


def test_hint_mentions_the_camera(make_window):
    window = _match_window(make_window)
    hint = window.match._hint_text()
    assert "滚轮" in hint and "拖" in hint, "无边界棋盘得告诉玩家能平移缩放"


def test_hive_uses_its_own_animation_setting(make_window):
    window = _match_window(make_window, hive_anim_ms=321)
    assert window.match._anim_ms() == 321


# --------------------------------------------------------------------------- #
# 大厅图标
# --------------------------------------------------------------------------- #

def test_lobby_hive_card_uses_the_hive_icon(make_window):
    window = make_window(start_scene="lobby")
    card = next(card for card in window.lobby._cards if card.game.key == "hive")
    assert card.game.icon == "hive"


def test_hive_icon_paints_something(make_window):
    """图标是手绘的六边形簇 —— 画错了会变成一片空白。"""
    window = make_window(start_scene="lobby")
    surface = pygame.Surface((120, 88))
    surface.fill((0, 0, 0))
    window.lobby._icon_hive(surface, pygame.Rect(0, 0, 120, 88))
    painted = sum(1 for x in range(0, 120, 2) for y in range(0, 88, 2)
                  if surface.get_at((x, y))[:3] != (0, 0, 0))
    assert painted > 40, "蜂巢图标几乎没画出东西"
