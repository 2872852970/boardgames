"""参数描述（ParamSpec）。

侧栏面板、JSON 持久化、以及 :class:`~boardgames.ai.engine.AIEngineParams`
的构造都从这份描述驱动 —— 想在界面上加一个可调参数，只要在这里加一行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParamKind = Literal["int", "float", "bool", "choice", "text"]

#: 分组 id → 中文标题（侧栏按此顺序展示）
GROUPS: tuple[tuple[str, str], ...] = (
    ("game", "棋局设置"),
    ("players", "对局双方"),
    ("minimax", "Minimax 参数"),
    ("mcts", "MCTS 参数"),
    ("eval", "评估权重"),
    ("ui", "界面与操作"),
)

#: 玩家类型（人 / AI / 随机）
PLAYER_TYPES: tuple[str, ...] = ("human", "minimax", "mcts", "random")
PLAYER_TYPE_LABELS: dict[str, str] = {
    "human": "人类",
    "minimax": "AI · Minimax",
    "mcts": "AI · MCTS",
    "random": "AI · 随机",
}

MODES: tuple[str, ...] = ("pvp", "pve", "eve")
MODE_LABELS: dict[str, str] = {
    "pvp": "双人对战",
    "pve": "人机对战",
    "eve": "AI 自对弈",
}


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: ParamKind
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    group: str = "game"
    hint: str = ""
    #: 是否出现在侧栏（关闭则只在 JSON 里可改）
    expose: bool = True
    #: 侧栏里默认折叠的高级参数
    advanced: bool = False
    #: 只在「有 AI 参战」时显示（例如 AI 落子停顿）
    needs_ai: bool = False
    #: 只在指定引擎参战时显示（"minimax" / "mcts"）
    needs_engine: str = ""
    #: 限定归属游戏（游戏 key 列表）；空元组 = 所有游戏都显示。
    #:
    #: 必须标对 —— 否则"棋盘尺寸""每人墙数"这类只对某个棋类有意义的参数，
    #: 会在别的棋类的侧栏里也露出来。
    games: tuple[str, ...] = ()

    # ---- 校验 / 归一化 ----

    def coerce(self, value: Any) -> Any:
        """把任意输入裁剪成合法值；无法解析时回落到默认值。"""
        try:
            if self.kind == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.strip().lower() in {"1", "true", "yes", "on", "是"}
                return bool(value)
            if self.kind == "int":
                out = int(round(float(value)))
            elif self.kind == "float":
                out = float(value)
            elif self.kind == "choice":
                text = str(value)
                return text if text in self.choices else self.default
            else:  # text
                return str(value)
        except (TypeError, ValueError):
            return self.default

        if self.minimum is not None:
            out = max(out, self.minimum)
        if self.maximum is not None:
            out = min(out, self.maximum)
        if self.kind == "int":
            return int(out)
        return float(out)


def _specs() -> list[ParamSpec]:
    # 常用缩写，避免下面每行都写 games=("quoridor",)
    Q = ("quoridor",)
    C4 = ("connect4",)
    out: list[ParamSpec] = [
        # ---------------- 棋局 ----------------
        ParamSpec("board_size", "棋盘尺寸", "int", 9, 5, 13, 2, group="game",
                  games=Q, hint="标准为 9×9"),
        ParamSpec("walls_per_player", "每人墙数", "int", 10, 0, 20, 1, group="game",
                  games=Q, hint="标准为 10 面"),
        ParamSpec("connect4_cols", "列数", "int", 7, 5, 12, 1, group="game",
                  games=C4, hint="标准为 7 列"),
        ParamSpec("connect4_rows", "行数", "int", 6, 4, 10, 1, group="game",
                  games=C4, hint="标准为 6 行"),
        ParamSpec("mode", "对局模式", "choice", "pve", choices=MODES, group="game"),
        ParamSpec("first_player", "先手", "choice", "p1", choices=("p1", "p2", "random"),
                  group="game", hint="数字版里的「石头剪刀布」"),
        # ---------------- 双方 ----------------
        ParamSpec("p1_type", "玩家 1", "choice", "human", choices=PLAYER_TYPES,
                  group="players"),
        ParamSpec("p2_type", "玩家 2", "choice", "minimax", choices=PLAYER_TYPES,
                  group="players"),
        # ---------------- Minimax ----------------
        ParamSpec("minimax_depth", "搜索深度", "int", 4, 1, 10, 1, group="minimax"),
        ParamSpec("minimax_wall_depth", "考虑放墙的层数", "int", 2, 1, 5, 1, group="minimax",
                  games=Q, hint="越大越强也越慢"),
        ParamSpec("minimax_max_branch", "墙候选上限", "int", 12, 0, 40, 1, group="minimax",
                  games=Q, hint="0 表示不裁剪（很慢）"),
        ParamSpec("minimax_time_ms", "思考时限 (ms)", "int", 1200, 50, 15000, 50, group="minimax"),
        ParamSpec("minimax_tt", "启用置换表", "bool", True, group="minimax", advanced=True),
        # ---------------- MCTS ----------------
        ParamSpec("mcts_iterations", "模拟次数", "int", 4000, 50, 200000, 50, group="mcts"),
        ParamSpec("mcts_c_uct", "探索常数 C", "float", 1.414, 0.1, 4.0, 0.05, group="mcts"),
        ParamSpec("mcts_rollout_cap", "Rollout 深度上限", "int", 40, 4, 200, 4, group="mcts",
                  advanced=True),
        ParamSpec("mcts_max_branch", "墙候选上限", "int", 8, 0, 40, 1, group="mcts", games=Q),
        ParamSpec("mcts_time_ms", "思考时限 (ms)", "int", 1200, 50, 15000, 50, group="mcts"),
        ParamSpec("ai_seed", "随机种子", "int", 0, 0, 10**9, 1, group="mcts", expose=False,
                  hint="0 表示每次随机；固定种子可复现对局"),
        # ---------------- 评估权重 ----------------
        ParamSpec("w_path", "最短路径差", "float", 100.0, 0.0, 400.0, 5.0, group="eval",
                  advanced=True, games=Q),
        ParamSpec("w_walls", "剩余墙数差", "float", 40.0, 0.0, 400.0, 5.0, group="eval",
                  advanced=True, games=Q),
        ParamSpec("w_mobility", "机动性差", "float", 6.0, 0.0, 100.0, 1.0, group="eval",
                  advanced=True, games=Q),
        ParamSpec("w_tempo", "节奏", "float", 5.0, 0.0, 100.0, 1.0, group="eval",
                  advanced=True, games=Q,
                  hint="轮到谁走的影响；四子棋双方完全对称，不适用"),
        ParamSpec("w_progress", "走子进度差", "float", 3.0, 0.0, 100.0, 1.0, group="eval",
                  advanced=True, games=Q),
        ParamSpec("p_wall", "Rollout 放墙概率", "float", 0.08, 0.0, 1.0, 0.01, group="eval",
                  advanced=True, needs_engine="mcts", games=Q, hint="放墙采样较贵，过高会拖慢 MCTS"),
        # 四子棋专属权重
        ParamSpec("w_material", "子数差", "float", 2.0, 0.0, 50.0, 0.5, group="eval",
                  advanced=True, games=C4, hint="已落子数之差"),
        ParamSpec("w_center", "中心列权重", "float", 8.0, 0.0, 50.0, 0.5, group="eval",
                  advanced=True, games=C4, hint="中间几列更容易连成四子"),
        ParamSpec("w_line", "连线长度", "float", 12.0, 0.0, 100.0, 1.0, group="eval",
                  advanced=True, games=C4, hint="活二 / 活三的潜在威胁"),
        ParamSpec("w_threat", "即时威胁", "float", 60.0, 0.0, 400.0, 5.0, group="eval",
                  advanced=True, games=C4,
                  hint="下一手就能连成四子的列数（攻防同权，保证评估对称）"),
        # ---------------- 界面 ----------------
        ParamSpec("anim_ms", "动画时长 (ms)", "int", 140, 0, 600, 10, group="ui"),
        ParamSpec("c4_anim_ms", "落子动画 (ms)", "int", 850, 0, 2000, 50, group="ui",
                  games=C4, hint="重力下落 + 回弹的总时长"),
        ParamSpec("show_hints", "显示合法落点提示", "bool", True, group="ui"),
        ParamSpec("show_wall_slots", "显示墙槽位", "bool", True, group="ui", games=Q),
        ParamSpec("ai_delay_ms", "AI 落子停顿 (ms)", "int", 120, 0, 3000, 20, group="ui",
                  needs_ai=True, hint="纯观感，不影响棋力"),
    ]
    return out


SPECS: tuple[ParamSpec, ...] = tuple(_specs())
SPEC_BY_KEY: dict[str, ParamSpec] = {spec.key: spec for spec in SPECS}

#: 每种引擎读取哪些参数（构建 AIEngineParams 用）
ENGINE_PARAM_MAP: dict[str, dict[str, str]] = {
    "minimax": {
        "time_limit_ms": "minimax_time_ms",
        "depth": "minimax_depth",
        "wall_depth": "minimax_wall_depth",
        "max_branch": "minimax_max_branch",
        "tt_enabled": "minimax_tt",
    },
    "mcts": {
        "time_limit_ms": "mcts_time_ms",
        "iterations": "mcts_iterations",
        "c_uct": "mcts_c_uct",
        "rollout_depth_cap": "mcts_rollout_cap",
        "max_branch": "mcts_max_branch",
    },
}

#: 所有引擎共享的评估权重键。
#:
#: 各棋类的 :func:`merged_weights` 会过滤掉不认识的键，所以把四子棋的权重也放进来
#: 不会干扰步步为营。
WEIGHT_KEYS: tuple[str, ...] = (
    "w_path",
    "w_walls",
    "w_mobility",
    "w_tempo",
    "w_progress",
    "p_wall",
    "w_material",
    "w_center",
    "w_line",
    "w_threat",
)


@dataclass
class Values:
    """参数值集合（键 → 值）。"""

    data: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        spec = SPEC_BY_KEY.get(key)
        self.data[key] = spec.coerce(value) if spec else value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)
