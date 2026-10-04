"""点格棋（Dots and Boxes）规则引擎。

规则要点
--------
* 双方轮流在相邻两点间画一条边（水平或垂直）。
* 画满一个方格的第四条边即**占领**该格，且**再走一手**（额外回合）。
* 所有边画完后，占领格子多者获胜；格子数打平则平局。
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import replace

from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.dotsboxes import heuristic as heu
from boardgames.games.dotsboxes.heuristic import evaluate as _evaluate_static
from boardgames.games.dotsboxes.move import EdgeMove
from boardgames.games.dotsboxes.state import (
    DEFAULT_SIZE,
    DotsBoxesState,
    initial_state,
)


class DotsBoxesGame(Game[DotsBoxesState, Move]):
    """点格棋。"""

    key = "dotsboxes"
    display_name = "点格棋"

    settings_map = {
        "dotsboxes_size": "size",
    }

    tagline = "Dots and Boxes · 围地盘"
    summary = "轮流在点阵上连线，画满一方格即占为己有并再走一手，格子多者胜。"
    goal = "所有边画完后占领格子更多"
    rules = (
        "盘面是 N×N 个点围成的 (N-1)×(N-1) 个方格（默认 6×6 点 = 5×5 方格）",
        "双方轮流在相邻两点间画一条边（水平或垂直）",
        "一条边只能画一次，不能重复",
        "画满一个方格的第四条边，即占领该格，由画这最后一条边的人获得",
        "占领格子后**再走一手**（额外回合），直到画出的边没有封住任何格子才换对方",
        "所有边都画完时游戏结束，占领格子多的一方获胜",
        "格子数打平则为平局",
    )
    howto = (
        "鼠标移到两个相邻点之间的边线上，点击画边",
        "悬停会高亮预览这条边（封口边用亮色提示）",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "优先抢「只剩一条边」的格子 —— 那是白送的，而且能连带走",
        "留一手「连击」：一条边同时封住两个格子能一次赚两份",
        "边上的格子往往比中心格子更容易先被人围住",
    )
    icon = "dotsboxes"

    def __init__(self, size: int = DEFAULT_SIZE, *, first_player: int = 0) -> None:
        self.size = int(size)
        self.first_player = first_player

    # ------------------------------------------------------------------ #
    # 基本信息
    # ------------------------------------------------------------------ #

    def player_count(self) -> int:
        return 2

    def player_meta(self) -> list[PlayerMeta]:
        return [
            PlayerMeta(name="玩家 1", color=(240, 185, 90)),   # 琥珀
            PlayerMeta(name="玩家 2", color=(91, 141, 239)),    # 蓝
        ]

    def initial_state(self, first_player: int | None = None) -> DotsBoxesState:
        return initial_state(
            self.size,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 着法生成
    # ------------------------------------------------------------------ #

    def _all_edges(self, state: DotsBoxesState) -> list[EdgeMove]:
        """所有还没画的边（画了就不算合法着法）。"""
        player = state.current
        moves: list[EdgeMove] = []
        for i, drawn in enumerate(state.h_edges):
            if not drawn:
                row, col = divmod(i, state.size - 1)
                moves.append(EdgeMove(0, row, col, player))
        for i, drawn in enumerate(state.v_edges):
            if not drawn:
                row, col = divmod(i, state.size)
                moves.append(EdgeMove(1, row, col, player))
        return moves

    def legal_moves(self, state: DotsBoxesState, options: SearchOptions | None = None) -> list[EdgeMove]:
        """合法着法 = 所有未画的边。

        分支因子开局 ``2*N*(N-1)``（6×6 点 = 60 条边），中局递减。不裁剪：
        分支最多也就一百上下，且点格棋的"封口边"不能被裁掉（裁掉等于让棋）。
        """
        if state.is_terminal():
            return []
        moves = self._all_edges(state)
        if options is not None and options.order:
            moves.sort(key=lambda m: self._order_key(state, m), reverse=True)
        return moves

    def _order_key(self, state: DotsBoxesState, move: EdgeMove) -> float:
        """排序：优先封口（能拿格）> 补到差一条边 > 随便画。

        封口边能拿格子（甚至连击），搜索时先试这些着法能显著加速剪枝。
        """
        closed = heu.boxes_closed_by_move(state, move.orient, move.row, move.col)
        if closed:
            return 1000.0 + len(closed) * 10.0
        # 其次：画了这条边后，相邻格子变成"差一条边"
        return self._after_value(state, move)

    def _after_value(self, state: DotsBoxesState, move: EdgeMove) -> float:
        """画这条边后，相邻格子的"还差几条边"里最接近封口的那条（越小越好）。"""
        best = 4
        for br, bc in heu.edge_closes_boxes(state, move.orient, move.row, move.col):
            if state.box_owner(br, bc) != 0:
                continue
            box_edges = heu._box_edges(state.size)[state.box_index(br, bc)]
            open_edges = heu._open_edges_for_box(state, box_edges)
            remaining = [e for e in open_edges if e != (move.orient, move.row, move.col)]
            best = min(best, len(remaining))
        return 4.0 - best  # 差 0 条 = 4 分（封口，但已被上面拦下），差 1 条 = 3 分 …

    def is_legal(self, state: DotsBoxesState, move: Move) -> bool:
        if not isinstance(move, EdgeMove):
            return False
        if state.is_terminal() or move.player != state.current:
            return False
        if move.orient not in (0, 1):
            return False
        if move.orient == 0:
            if not (0 <= move.row < state.size and 0 <= move.col < state.size - 1):
                return False
            return state.h_edges[state.h_index(move.row, move.col)] == 0
        if not (0 <= move.row < state.size - 1 and 0 <= move.col < state.size):
            return False
        return state.v_edges[state.v_index(move.row, move.col)] == 0

    def apply(self, state: DotsBoxesState, move: Move) -> DotsBoxesState:
        """画一条边。封住格子则同玩家继续，否则换人。返回新对象。"""
        if not self.is_legal(state, move):
            raise ValueError(f"非法着法: {move}")

        player = state.current
        h_edges = state.h_edges
        v_edges = state.v_edges
        who = player + 1
        if move.orient == 0:
            i = state.h_index(move.row, move.col)
            h_edges = h_edges[:i] + (who,) + h_edges[i + 1:]
        else:
            i = state.v_index(move.row, move.col)
            v_edges = v_edges[:i] + (who,) + v_edges[i + 1:]

        # 封住的格子
        closed = heu.boxes_closed_by_move(state, move.orient, move.row, move.col)
        boxes = state.boxes
        scores = state.scores
        if closed:
            boxes = list(boxes)
            new_count = 0
            for br, bc in closed:
                bi = state.box_index(br, bc)
                boxes[bi] = player + 1
                new_count += 1
            boxes = tuple(boxes)
            scores = (
                (scores[0] + new_count, scores[1])
                if player == 0
                else (scores[0], scores[1] + new_count)
            )

        # 胜负判定：所有边画完
        winner = state.winner_player
        if (
            winner is None
            and state.ply + 1 >= state.size * (state.size - 1) * 2
            and scores[0] != scores[1]
        ):
            winner = 0 if scores[0] > scores[1] else 1

        # 封口 → 同玩家继续（额外回合）；没封口 → 换人
        nxt = player if closed else 1 - player

        return replace(
            state,
            h_edges=h_edges,
            v_edges=v_edges,
            boxes=boxes,
            scores=scores,
            current=nxt,
            ply=state.ply + 1,
            winner_player=winner,
        )

    # ------------------------------------------------------------------ #
    # 评估与模拟
    # ------------------------------------------------------------------ #

    def evaluate(
        self, state: DotsBoxesState, player: int, weights: Mapping[str, float] | None = None
    ) -> float:
        return _evaluate_static(state, player, weights)

    def rollout_move(
        self,
        state: DotsBoxesState,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> EdgeMove:
        """rollout 策略：优先封口（拿格子），否则随机画边。

        收敛性天然成立：每步必然 ``ply += 1`` 且边数单调减少，任何合法着法
        序列都必然在有限步内画完所有边。
        """
        moves = self._all_edges(state)
        if not moves:
            raise RuntimeError("局面已终局，不该再请求 rollout 着法")

        closing = [
            m for m in moves
            if heu.boxes_closed_by_move(state, m.orient, m.row, m.col)
        ]
        if closing:
            # 封口边里优先连击（一次封多个）
            best = max(closing, key=lambda m: len(heu.boxes_closed_by_move(state, m.orient, m.row, m.col)))
            return best

        # 随机画一条，但稍微偏向"接近封口"的边
        scored = sorted(moves, key=lambda m: self._after_value(state, m), reverse=True)
        top = scored[: max(1, len(scored) // 3)]
        return rng.choice(top)

    # ------------------------------------------------------------------ #
    # 提示
    # ------------------------------------------------------------------ #

    def describe_state(self, state: DotsBoxesState) -> str:
        if state.winner_player is not None:
            return f"{self.player_meta()[state.winner_player].name}占领格子更多"
        if state.is_terminal():
            return "平局"
        return f"{self.player_meta()[state.current].name}画边"

    def move_hints(self, state: DotsBoxesState) -> dict[str, object]:
        return {"scores": state.scores}


DEFAULT_OPTIONS = SearchOptions()
__all__ = ["DotsBoxesGame", "DotsBoxesState", "EdgeMove", "DEFAULT_OPTIONS"]
