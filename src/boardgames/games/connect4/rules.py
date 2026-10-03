"""重力四子棋（Connect Four）规则引擎。

规则要点
--------
* 双方轮流向**任一未满列**投一枚棋子，棋子因重力落到该列最低空位。
* 横 / 竖 / 斜**任一方向连续四子**即胜。
* 棋盘填满仍无人连成四子则**平局**。
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import replace

from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.connect4 import heuristic as heu
from boardgames.games.connect4.heuristic import (
    evaluate as _evaluate_static,
)
from boardgames.games.connect4.move import DropMove
from boardgames.games.connect4.state import (
    CONNECT_TO,
    DEFAULT_COLS,
    DEFAULT_ROWS,
    Connect4State,
    initial_state,
    scan_win,
)


class Connect4Game(Game[Connect4State, Move]):
    """重力四子棋。"""

    key = "connect4"
    display_name = "重力四子棋"

    settings_map = {
        "connect4_cols": "cols",
        "connect4_rows": "rows",
        "first_player": "first_player",
    }

    tagline = "Connect Four · 重力落子"
    summary = "轮流往任意一列投子，横竖斜任一方向先连成四子者胜。"
    goal = "横、竖、斜任一方向先连成四子"
    rules = (
        "双方轮流从顶部往任意一列投子，棋子沿重力落到该列最低的空位",
        "棋子不能悬空：每一列都是从下往上堆，没有「放错位置」这回事",
        "某一列堆满之后，就不能再往这一列投子",
        "横 / 竖 / 斜任一方向连续四子即胜",
        "棋盘填满仍无人连成四子，判平局",
        "棋盘尺寸可调（默认 7 列 × 6 行），列数行数都算进 AI 的评估里",
    )
    howto = (
        "鼠标移到某一列上会显示落点预览，点击投子",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "先手（玩家 1）占住中间列通常最划算 —— 中间列参与的四连方向最多",
        "真正致命的是「双威胁」：一手之后同时有两个位置能连成四子",
    )
    icon = "drop"

    def __init__(
        self,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
        *,
        first_player: int = 0,
    ) -> None:
        self.cols = int(cols)
        self.rows = int(rows)
        self.first_player = first_player

    # ------------------------------------------------------------------ #
    # 基本信息
    # ------------------------------------------------------------------ #

    def player_count(self) -> int:
        return 2

    def player_meta(self) -> list[PlayerMeta]:
        # 颜色用 RGB 字面量而不是 ui.theme.P0/P1 —— core 层不得依赖 pygame 侧模块。
        # 这两个值与 theme.P0 / theme.P1 一致，改主题时这里要同步。
        return [
            PlayerMeta(name="玩家 1", color=(240, 185, 90)),   # 琥珀
            PlayerMeta(name="玩家 2", color=(91, 141, 239)),    # 蓝
        ]

    def initial_state(self, first_player: int | None = None) -> Connect4State:
        return initial_state(
            self.cols,
            self.rows,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 着法生成
    # ------------------------------------------------------------------ #

    def open_columns(self, state: Connect4State) -> list[int]:
        """所有还没满的列。"""
        return [c for c in range(state.cols) if state.heights[c] < state.rows]

    def legal_moves(self, state: Connect4State, options: SearchOptions | None = None) -> list[DropMove]:
        """合法着法 = 投进任一未满列。

        **刻意忽略** ``options.max_branch`` 与 ``options.include_walls``：

        * 分支因子 = 未满列数（最多 12）本来就小于 ``max_branch`` 默认值 16，裁剪无意义；
        * ``include_walls`` 更是 Quoridor 专属 —— minimax 会按
          ``include_walls = ply < wall_depth`` 逐层关闭它。若把它解读为
          "裁剪着法"，深度 ≥2 的节点就只剩一个着法，棋力会直接崩掉。
          对四子棋来说这两个标志没有任何语义，一律忽略。
        """
        if state.is_terminal():
            return []
        player = state.current
        cols = self.open_columns(state)
        if options is not None and options.order:
            # 中心列优先（经典启发式：中间列能连成的方向最多）
            weights = heu.center_weights(state.cols)
            cols = sorted(cols, key=lambda c: -weights[c])
        return [DropMove(c, state.heights[c], player) for c in cols]

    def is_legal(self, state: Connect4State, move: Move) -> bool:
        if not isinstance(move, DropMove):
            return False
        if state.is_terminal():
            return False
        if not (0 <= move.col < state.cols):
            return False
        # 重力规则：只能落在该列当前最低的空位
        return move.row == state.heights[move.col]

    def apply(self, state: Connect4State, move: Move) -> Connect4State:
        """落子。返回**新**对象，不改入参。"""
        if not self.is_legal(state, move):
            raise ValueError(f"非法着法: {move}")
        player = state.current
        who = player + 1
        col, row = move.col, move.row
        index = row * state.cols + col
        cells = state.cells[:index] + (who,) + state.cells[index + 1:]
        heights = state.heights[:col] + (row + 1,) + state.heights[col + 1:]

        winner = state.winner_player
        if winner is None and scan_win(cells, state.cols, state.rows, row, col, who):
            # ``scan_win`` 用棋子值（1/2）判定，这里转成玩家索引（0/1）缓存，
            # 与 State.current_player / GameSession.winner() 保持同一套语义
            winner = player

        return replace(
            state,
            cells=cells,
            heights=heights,
            current=1 - player,
            ply=state.ply + 1,
            winner_player=winner,
        )

    # ------------------------------------------------------------------ #
    # 评估与模拟
    # ------------------------------------------------------------------ #

    def evaluate(
        self, state: Connect4State, player: int, weights: Mapping[str, float] | None = None
    ) -> float:
        return _evaluate_static(state, player, weights)

    def rollout_move(
        self,
        state: Connect4State,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> DropMove:
        """rollout 策略：贪婪 + 中心优先，``rng`` 只用于同分打破。

        收敛性天然成立：四子棋每步必然 ``ply += 1`` 且棋盘不可逆地填满，
        任何合法着法序列都必然在 ≤ ``cols * rows`` 步内终止 —— 不像墙棋的棋子
        可以来回走，振荡在数学上不可能发生。
        """
        cols = self.open_columns(state)
        if not cols:
            raise RuntimeError("局面已终局，不该再请求 rollout 着法")
        player = state.current
        opp = 1 - player

        # 1) 能立刻赢就赢
        for col in cols:
            if self._would_win(state, col, player):
                return DropMove(col, state.heights[col], player)

        # 2) 对手能立刻赢就必须堵（多个威胁时堵离中心近的那个）
        threats = [c for c in cols if self._would_win(state, c, opp)]
        if threats:
            weights = heu.center_weights(state.cols)
            best = max(threats, key=lambda c: weights[c])
            return DropMove(best, state.heights[best], player)

        # 3) 否则按中心权重加权随机，保留多样性
        position = heu.center_weights(state.cols)
        chosen = rng.choices(cols, weights=[position[c] for c in cols], k=1)[0]
        return DropMove(chosen, state.heights[chosen], player)

    def _would_win(self, state: Connect4State, col: int, player: int) -> bool:
        row = state.heights[col]
        if row >= state.rows:
            return False
        return heu._connects_at(state, col, row, player + 1)

    # ------------------------------------------------------------------ #
    # 提示
    # ------------------------------------------------------------------ #

    def describe_state(self, state: Connect4State) -> str:
        if state.winner_player is not None:
            name = self.player_meta()[state.winner_player].name
            return f"{name} 连成四子"
        if state.is_full():
            return "棋盘已满 · 平局"
        return f"{self.player_meta()[state.current].name} 投子"

    def move_hints(self, state: Connect4State) -> dict[str, object]:
        return {"columns": tuple(self.open_columns(state))}


DEFAULT_OPTIONS = SearchOptions()
#: 供测试与外部引用的常量
__all__ = ["Connect4Game", "Connect4State", "DropMove", "CONNECT_TO", "DEFAULT_OPTIONS"]
