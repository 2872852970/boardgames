"""极小极大搜索：负极大值 + Alpha-Beta 剪枝 + 迭代加深 + 置换表。

搜索状态全部放在 :class:`_MinimaxRun` 里（每次搜索一个实例），
因此引擎对象本身是**无状态**的 —— 取消后立刻重开新搜索也不会互相串味。
"""

from __future__ import annotations

import time

from boardgames.ai.engine import (
    AIEngine,
    AIEngineParams,
    SearchContext,
    SearchResult,
    SearchStats,
)
from boardgames.ai.tt import EXACT, LOWER, UPPER, TranspositionTable, TTEntry
from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.state import State

INF = float("inf")
MATE = 100_000.0
#: 只把"非绝杀"分数写进置换表，避免与 ply 相关的绝杀距离被跨层错误复用。
TT_MATE_GUARD = 1000.0


class _MinimaxRun:
    """一次搜索的全部可变状态。"""

    __slots__ = ("game", "params", "ctx", "weights", "tt", "nodes")

    def __init__(self, game: Game, params: AIEngineParams, ctx: SearchContext) -> None:
        self.game = game
        self.params = params
        self.ctx = ctx
        self.weights = dict(params.weights)
        self.tt = TranspositionTable() if params.tt_enabled else None
        self.nodes = 0

    def options(self, ply: int) -> SearchOptions:
        return SearchOptions(
            max_branch=self.params.max_branch,
            order=ply <= 1,
            include_walls=ply < max(1, self.params.wall_depth),
        )

    # ------------------------------------------------------------------ #

    def root_search(
        self, state: State, depth: int
    ) -> tuple[float, Move] | None:
        alpha = -INF
        best_score = -INF
        best_move: Move | None = None
        player = state.current_player
        for move in self.game.legal_moves(state, self.options(0)):
            child = self.game.apply(state, move)
            if child.current_player == player:
                # 额外回合：同一玩家继续，视角不变，用 (alpha, INF) 窗口且不取反
                value = self.negamax(child, depth - 1, alpha, INF, 1)
            else:
                value = self.negamax(child, depth - 1, -INF, -alpha, 1)
                if value is not None:
                    value = -value
            if value is None:
                return None
            score = value
            if score > best_score:
                best_score, best_move = score, move
            if score > alpha:
                alpha = score
        if best_move is None:
            return None
        return best_score, best_move

    def negamax(
        self, state: State, depth: int, alpha: float, beta: float, ply: int
    ) -> float | None:
        self.nodes += 1
        if self.ctx.should_stop():
            return None

        player = state.current_player
        if state.is_terminal():
            winner = state.winner()
            if winner is None:
                return 0.0
            return (MATE - ply) if winner == player else -(MATE - ply)
        if depth <= 0:
            return self.game.evaluate(state, player, self.weights)

        key = state.zobrist_hash()
        tt_move: Move | None = None
        if self.tt is not None:
            entry = self.tt.get(key)
            if entry is not None:
                tt_move = entry.move
                if entry.depth >= depth:
                    if entry.flag == EXACT:
                        return entry.score
                    if entry.flag == LOWER and entry.score >= beta:
                        return entry.score
                    if entry.flag == UPPER and entry.score <= alpha:
                        return entry.score

        moves = self.game.legal_moves(state, self.options(ply))
        if not moves:
            return 0.0
        if tt_move is not None:
            for i, candidate in enumerate(moves):
                if candidate == tt_move:
                    moves.insert(0, moves.pop(i))
                    break

        best = -INF
        best_move = None
        a = alpha
        for move in moves:
            child = self.game.apply(state, move)
            if child.current_player == player:
                # 额外回合（点格棋封口、播棋落己方仓库）：同一玩家继续走，
                # 视角不变，**不能**取反。alpha/beta 也不换边。
                value = self.negamax(child, depth - 1, a, beta, ply + 1)
            else:
                value = self.negamax(child, depth - 1, -beta, -a, ply + 1)
                if value is not None:
                    value = -value
            if value is None:
                return None
            score = value
            if score > best:
                best, best_move = score, move
            if score > a:
                a = score
            if a >= beta:
                break

        # 只有完整跑完的搜索才写置换表（被时间截断的会污染后续搜索）
        if self.tt is not None and abs(best) < MATE - TT_MATE_GUARD:
            if best <= alpha:
                flag = UPPER
            elif best >= beta:
                flag = LOWER
            else:
                flag = EXACT
            self.tt.put(key, TTEntry(depth, flag, best, best_move))
        return best


class MinimaxEngine(AIEngine):
    """深度优先 + 剪枝的经典搜索。

    面对 Quoridor 巨大的墙分支，靠两层手段把分支压下来：

    1. 每个节点只考虑"对手最短路径附近"的少量墙候选（由游戏实现提供）；
    2. 超过 ``wall_depth`` 层之后只展开走子。
    """

    key = "minimax"
    display_name = "极小极大 (Alpha-Beta)"
    param_groups = ("minimax",)

    def __init__(self) -> None:
        #: 上一次搜索的上下文，仅供调试/统计查看，不参与搜索逻辑
        self.last_run: _MinimaxRun | None = None

    def search(
        self,
        game: Game,
        state: State,
        player: int,
        params: AIEngineParams,
        ctx: SearchContext,
    ) -> SearchResult:
        t0 = time.perf_counter()
        run = _MinimaxRun(game, params, ctx)
        self.last_run = run

        stats = SearchStats(engine=self.key, engine_name=self.display_name)
        if state.is_terminal() or not game.legal_moves(state, run.options(0)):
            stats.elapsed_ms = (time.perf_counter() - t0) * 1000
            return SearchResult(None, stats)

        best_move: Move | None = None
        best_score: float | None = None

        # 迭代加深：只采纳"完整跑完"的那一层，被时间截断的层丢弃
        for depth in range(1, max(1, params.depth) + 1):
            if ctx.should_stop():
                break
            outcome = run.root_search(state, depth)
            if outcome is None:
                break
            best_score, best_move = outcome
            stats.depth_reached = depth
            if abs(best_score) >= MATE - TT_MATE_GUARD:
                break  # 已经找到必胜/必败
            if ctx.time_up():
                break

        stats.nodes = run.nodes
        stats.score = best_score
        stats.elapsed_ms = (time.perf_counter() - t0) * 1000
        stats.cancelled = ctx.cancelled
        if best_move is None:
            return SearchResult(None, stats)
        return SearchResult(best_move, stats)

    # ---- 便于测试/调试的只读视图 ----

    @property
    def tt(self) -> TranspositionTable | None:
        return self.last_run.tt if self.last_run is not None else None

    @property
    def nodes(self) -> int:
        return self.last_run.nodes if self.last_run is not None else 0
