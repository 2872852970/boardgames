"""蒙特卡洛树搜索（UCT）。

与 Minimax 一样，搜索状态放在每次搜索独立的 :class:`_MCTSRun` 里，
引擎对象本身无状态 —— 取消后立刻重开新搜索也不会互相串味。
"""

from __future__ import annotations

import math
import random
import time

from boardgames.ai.engine import (
    AIEngine,
    AIEngineParams,
    SearchContext,
    SearchResult,
    SearchStats,
)
from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.state import State

#: 达到 rollout 深度上限时，把静态评估压到 [-1, 1] 的尺度。
ROLLOUT_VALUE_SCALE = 600.0


class _Node:
    __slots__ = ("state", "parent", "move", "player", "children", "untried", "visits", "total")

    def __init__(self, state: State, parent: _Node | None, move: Move | None) -> None:
        self.state = state
        self.parent = parent
        self.move = move
        #: 轮到谁在这个节点行动；total 记的是**该玩家视角**的累计收益
        self.player = state.current_player
        self.children: dict[Move, _Node] = {}
        #: ``None`` 表示"着法尚未生成"（惰性展开，省掉大量无用计算）
        self.untried: list[Move] | None = None
        self.visits = 0
        self.total = 0.0

    @property
    def mean(self) -> float:
        return self.total / self.visits if self.visits else 0.0


class _MCTSRun:
    """一次 MCTS 搜索的全部状态。"""

    __slots__ = ("game", "params", "ctx", "root_player", "rng", "options")

    def __init__(
        self,
        game: Game,
        params: AIEngineParams,
        ctx: SearchContext,
        root_player: int,
    ) -> None:
        self.game = game
        self.params = params
        self.ctx = ctx
        self.root_player = root_player
        self.rng = random.Random(params.seed)
        self.options = SearchOptions(
            max_branch=params.max_branch,
            order=False,
            include_walls=True,
        )

    # ---- 四阶段：选择 / 扩展 / 模拟 / 回溯 ----

    def select(self, root: _Node) -> _Node:
        node = root
        while self._is_expandable(node):
            node = self.best_child(node)
        return node

    @staticmethod
    def _is_expandable(node: _Node) -> bool:
        """是否可以继续往下走（即：该节点已完全展开且有子节点）。"""
        if node.state.is_terminal():
            return False
        if node.untried is None:
            return False  # 还没生成过着法 → 停在这里去生成
        if node.untried:
            return False  # 还有没试过的着法
        return bool(node.children)

    def best_child(self, node: _Node) -> _Node:
        log_n = math.log(node.visits + 1.0)
        best_child = None
        best_value = -math.inf
        for child in node.children.values():
            exploit = -child.mean  # 子节点存的是对手视角，取负才是本方视角
            explore = self.params.c_uct * math.sqrt(log_n / (child.visits + 1.0))
            value = exploit + explore
            if value > best_value:
                best_value, best_child = value, child
        assert best_child is not None
        return best_child

    def expand(self, node: _Node) -> _Node:
        if node.state.is_terminal():
            return node
        if node.untried is None:
            node.untried = self.game.legal_moves(node.state, self.options)
        if not node.untried:
            return node
        index = self.rng.randrange(len(node.untried))
        move = node.untried.pop(index)
        child_state = self.game.apply(node.state, move)
        child = _Node(child_state, node, move)
        node.children[move] = child
        return child

    def rollout(self, state: State) -> float:
        """返回**从根玩家视角**的回报，范围 [-1, 1]。"""
        current = state
        depth = 0
        cap = max(1, self.params.rollout_depth_cap)
        while not current.is_terminal() and depth < cap:
            if self.ctx.should_stop():
                break
            move = self.game.rollout_move(current, self.rng, None, self.params.weights)
            current = self.game.apply(current, move)
            depth += 1

        winner = current.winner()
        if winner is not None:
            base = 1.0 if winner == self.root_player else -1.0
            # 「越快分出胜负越好」：避免胜率已接近 1 时来回拖延
            speed = max(0.5, 1.0 - depth / (2.0 * cap))
            return base * speed
        score = self.game.evaluate(current, self.root_player, self.params.weights)
        return math.tanh(score / ROLLOUT_VALUE_SCALE)

    def backup(self, node: _Node | None, value: float) -> None:
        """``value`` 是根玩家视角的回报，回溯时按各节点的行动方翻符号。"""
        while node is not None:
            node.visits += 1
            node.total += value if node.player == self.root_player else -value
            node = node.parent

    @staticmethod
    def depth_of(node: _Node) -> int:
        depth = 0
        while node.parent is not None:
            depth += 1
            node = node.parent
        return depth


class MCTSEngine(AIEngine):
    """UCB1 选点 + 启发式 rollout 的 MCTS。"""

    key = "mcts"
    display_name = "蒙特卡洛树搜索 (UCT)"
    param_groups = ("mcts",)

    def __init__(self) -> None:
        self.last_run: _MCTSRun | None = None

    def search(
        self,
        game: Game,
        state: State,
        player: int,
        params: AIEngineParams,
        ctx: SearchContext,
    ) -> SearchResult:
        t0 = time.perf_counter()
        run = _MCTSRun(game, params, ctx, player)
        self.last_run = run

        stats = SearchStats(engine=self.key, engine_name=self.display_name)
        root_moves = game.legal_moves(state, run.options)
        if not root_moves:
            stats.elapsed_ms = (time.perf_counter() - t0) * 1000
            return SearchResult(None, stats)

        # 立刻能赢就直接赢（省掉整棵树的搜索）
        for move in root_moves:
            child = game.apply(state, move)
            if child.is_terminal() and child.winner() == player:
                stats.elapsed_ms = (time.perf_counter() - t0) * 1000
                stats.iterations = 1
                stats.depth_reached = 1
                stats.win_rate = 1.0
                return SearchResult(move, stats)

        root = _Node(state, None, None)
        root.untried = list(root_moves)

        iterations = 0
        while iterations < max(1, params.iterations):
            if ctx.should_stop():
                break
            iterations += 1
            node = run.expand(run.select(root))
            run.backup(node, run.rollout(node.state))

        stats.iterations = iterations
        stats.elapsed_ms = (time.perf_counter() - t0) * 1000
        stats.cancelled = ctx.cancelled

        if not root.children:
            return SearchResult(run.rng.choice(root_moves), stats)

        # 注意：子节点的 mean 是**子节点行动方**视角，必须翻符号才是根玩家视角。
        def root_value(node: _Node) -> float:
            return node.mean if node.player == player else -node.mean

        best = max(root.children.values(), key=lambda c: (round(root_value(c), 2), c.visits))
        stats.win_rate = root_value(best)
        stats.score = stats.win_rate
        stats.depth_reached = run.depth_of(best)
        return SearchResult(best.move, stats)
