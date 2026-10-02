"""参数系统的校验与持久化。"""

from __future__ import annotations

import json

from boardgames.settings import SPEC_BY_KEY, Settings
from boardgames.settings.store import SCHEMA_VERSION


def test_defaults_are_complete():
    settings = Settings()
    for spec in SPEC_BY_KEY.values():
        assert spec.key in settings.as_dict()
        assert settings.get(spec.key) == spec.default


def test_out_of_range_values_are_clamped():
    settings = Settings()
    assert settings.set("minimax_depth", 999) == SPEC_BY_KEY["minimax_depth"].maximum
    assert settings.set("minimax_depth", -5) == SPEC_BY_KEY["minimax_depth"].minimum
    assert settings.set("mcts_c_uct", 99.0) == SPEC_BY_KEY["mcts_c_uct"].maximum


def test_choice_falls_back_to_default():
    settings = Settings()
    assert settings.set("mode", "nonsense") == SPEC_BY_KEY["mode"].default
    assert settings.set("mode", "eve") == "eve"


def test_bool_coercion():
    settings = Settings()
    assert settings.set("show_hints", "false") is False
    assert settings.set("show_hints", "yes") is True
    assert settings.set("show_hints", 0) is False


def test_unknown_keys_are_discarded_on_load(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "params": {"minimax_depth": 3, "不存在的键": 123},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    settings = Settings.load(path)
    assert settings.get("minimax_depth") == 3
    assert "不存在的键" not in settings.as_dict()


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json ", encoding="utf-8")
    settings = Settings.load(path)
    assert settings.get("minimax_depth") == SPEC_BY_KEY["minimax_depth"].default


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(path)
    settings.set("board_size", 7)
    settings.set("walls_per_player", 5)
    settings.set("p2_type", "mcts")
    settings.save()
    assert path.exists()

    reloaded = Settings.load(path)
    assert reloaded.get("board_size") == 7
    assert reloaded.get("walls_per_player") == 5
    assert reloaded.get("p2_type") == "mcts"


def test_change_listeners_fire():
    settings = Settings()
    seen: list[tuple[str, object]] = []
    settings.on_change(lambda k, v: seen.append((k, v)))
    settings.set("minimax_depth", 5)
    assert seen == [("minimax_depth", 5)]


def test_reset_restores_defaults():
    settings = Settings()
    settings.set("board_size", 11)
    settings.reset()
    assert settings.get("board_size") == SPEC_BY_KEY["board_size"].default


def test_engine_params_mapping():
    settings = Settings()
    settings.set("minimax_depth", 6)
    settings.set("minimax_wall_depth", 3)
    settings.set("minimax_max_branch", 20)
    settings.set("minimax_time_ms", 700)
    settings.set("ai_seed", 42)

    params = settings.engine_params("minimax")
    assert params.depth == 6
    assert params.wall_depth == 3
    assert params.max_branch == 20
    assert params.time_limit_ms == 700
    assert params.seed == 42
    assert params.weights["w_path"] == settings.get("w_path")

    mcts = settings.engine_params("mcts")
    assert mcts.iterations == settings.get("mcts_iterations")
    assert mcts.c_uct == settings.get("mcts_c_uct")
    assert mcts.seed == 42

    # 未知引擎 → 只有权重与种子
    other = settings.engine_params("random")
    assert other.weights
    assert other.time_limit_ms == 1200  # AIEngineParams 的默认值


def test_zero_seed_means_random():
    settings = Settings()
    settings.set("ai_seed", 0)
    assert settings.engine_params("mcts").seed is None


def test_set_unknown_key_raises():
    import pytest

    settings = Settings()
    with pytest.raises(KeyError):
        settings.set("没有这个参数", 1)


def test_volatile_values_are_not_persisted(tmp_path):
    """命令行覆盖不应写进配置文件。"""
    path = tmp_path / "settings.json"
    settings = Settings(path)
    settings.set("board_size", 9)

    settings.set_volatile("board_size", 11)
    settings.set_volatile("mode", "eve")
    settings.set("minimax_depth", 5)  # 正常修改应当落盘
    assert settings.get("board_size") == 11  # 本进程内生效
    settings.save()

    reloaded = Settings.load(path)
    assert reloaded.get("board_size") == 9     # 覆盖未落盘
    assert reloaded.get("mode") != "eve"
    assert reloaded.get("minimax_depth") == 5  # 正常修改已落盘


def test_volatile_knows_unknown_key():
    import pytest

    settings = Settings()
    with pytest.raises(KeyError):
        settings.set_volatile("不存在", 1)
