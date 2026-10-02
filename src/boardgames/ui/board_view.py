"""棋盘视图协议（可插拔）。

框架只约定这几个方法，具体怎么画由各棋类自己决定 ——
墙棋的槽位、围棋的点、国象的格子差异太大，强做一个"通用棋盘渲染器"反而难维护。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pygame

from boardgames.core.game import Game
from boardgames.core.move import Move
from boardgames.core.state import State
from boardgames.ui.fonts import FontBook


@dataclass
class ViewState:
    """与规则无关的视图状态。

    "放墙还是走子"这类判定由各游戏的视图根据鼠标位置自行推导，
    因此这里不再有 ``placing`` 之类的模式开关。
    """

    #: 鼠标位置
    mouse: tuple[int, int] = (0, 0)
    #: 当前可交互的玩家；None 表示不可交互
    interactive_player: int | None = None
    #: 是否禁用输入（AI 思考中 / 动画播放中）
    input_locked: bool = False
    #: 棋类自定义的额外状态（例如 ``hover_kind``）
    extra: dict[str, Any] = field(default_factory=dict)

    def flag(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key, default)


@runtime_checkable
class BoardView(Protocol):
    """棋盘渲染 + 命中测试 + 动画。"""

    def layout(self, area: pygame.Rect) -> None:
        """根据可用区域重新计算布局。"""

    def draw(
        self,
        surface: pygame.Surface,
        fonts: FontBook,
        game: Game,
        state: State,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        """整块棋盘 + 叠加层。"""

    def handle_click(
        self, pos: tuple[int, int], game: Game, state: State, view: ViewState
    ) -> Move | None:
        """把一次点击翻译成一步着法；无法解释时返回 ``None``。"""

    def handle_motion(
        self, pos: tuple[int, int], game: Game, state: State, view: ViewState
    ) -> None:
        """更新悬停高亮 / 幽灵预览。"""

    def animate(self, move: Move, duration_ms: int) -> None:
        """为一步着法播放入场动画。"""

    def update(self, dt_ms: float) -> bool:
        """推进动画；返回是否仍在播放。"""

    def is_animating(self) -> bool:
        """动画是否在播放中（用于锁定输入）。"""

    def reset(self) -> None:
        """清空选中/动画（新局、悔棋时调用）。"""

    def set_last_move(self, move: Move | None) -> None:
        """记录最后一手，用于高亮。"""
