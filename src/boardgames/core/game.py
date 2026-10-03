"""游戏规则引擎抽象 —— 扩展新棋类的唯一契约。"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.core.state import State


@dataclass(frozen=True)
class SearchOptions:
    """搜索期着法生成的裁剪与排序选项。

    Quoridor 这类游戏的分支因子可能上百（走子 ≤5 + 墙位上百），
    不裁剪则搜索深度毫无意义。具体裁剪策略由各游戏自行实现。
    """

    #: 组合爆炸型着法（如放墙）的候选数量上限；0 表示不限制。
    max_branch: int = 16
    #: 是否对返回的着法排序（排序有价值但更慢，浅层可关闭）。
    order: bool = True
    #: 是否包含跳过型着法（跳跃、吃过路兵等）。默认包含。
    include_special: bool = True
    #: 是否生成"组合爆炸型"着法（如放墙）。深层搜索关掉它可以极大降低分支。
    include_walls: bool = True


#: 默认的搜索裁剪选项。
FULL_SEARCH = SearchOptions(max_branch=0, order=False)


class Game[S: State, M: Move](ABC):
    """一个棋类的规则引擎。

    AI（Minimax / MCTS）只依赖本接口，因此接入新棋类时 **AI 侧零改动**。
    """

    #: 机器可读的短名，用于注册表和配置持久化。
    key: ClassVar[str]
    #: 中文展示名。
    display_name: ClassVar[str]

    #: settings 键 → 构造函数参数名。空 dict 表示该游戏不读任何设置参数。
    #:
    #: :class:`~boardgames.controller.session.GameSession` 靠它把侧栏参数注入规则引擎。
    #: 必须是纯 ClassVar（不能 import settings）——``settings.store`` 已经依赖
    #: ``ai.engine``，core 再反向 import 会成环。
    settings_map: ClassVar[Mapping[str, str]] = {}

    # ---- 大厅卡片元数据（纯数据，供游戏选择大厅使用） ----
    #: 副标题，例如 ``"Quoridor · 墙棋"``。
    tagline: ClassVar[str] = ""
    #: 一句话简介。
    summary: ClassVar[str] = ""
    #: 玩法要点（每条一行）。
    rules: ClassVar[tuple[str, ...]] = ()
    #: 卡片图标样式：``"board"`` / ``"drop"`` / ``"dots"``（由大厅负责绘制）。
    icon: ClassVar[str] = "dots"

    # ---- 基本信息 ----

    @abstractmethod
    def player_count(self) -> int:
        """玩家数量（本文档框架默认 2）。"""

    @abstractmethod
    def player_meta(self) -> list[PlayerMeta]:
        """各玩家的展示信息。"""

    # ---- 规则 ----

    @abstractmethod
    def initial_state(self) -> S:
        """初始局面。"""

    @abstractmethod
    def legal_moves(self, state: S, options: SearchOptions | None = None) -> list[M]:
        """当前玩家的合法着法。

        - `options is None`：返回**全部**合法着法（UI 用）。
        - 否则按 `options` 裁剪并排序（搜索用）。
        """

    @abstractmethod
    def is_legal(self, state: S, move: M) -> bool:
        """单步合法性校验（UI 兜底与契约测试用）。"""

    @abstractmethod
    def apply(self, state: S, move: M) -> S:
        """执行着法，返回**新**状态。不得修改入参。"""

    # ---- 评估与模拟 ----

    @abstractmethod
    def evaluate(self, state: S, player: int, weights: Mapping[str, float] | None = None) -> float:
        """以 `player` 为视角的静态评估分（越大越好）。"""

    @abstractmethod
    def rollout_move(
        self,
        state: S,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> M:
        """MCTS rollout 用的默认策略（`weights` 可携带 rollout 相关旋钮）。"""

    # ---- 可选钩子（UI 用，默认空实现） ----

    def move_hints(self, state: S) -> dict[str, object]:
        """给 UI 的提示信息，例如 `{"targets": {...}}`。默认无。"""
        return {}

    def describe_state(self, state: S) -> str:
        """一句局面描述，用于状态栏/日志。"""
        return ""
