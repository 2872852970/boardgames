"""对局会话：局面、历史、模式调度、悔棋、AI 编排。

UI 只通过本类与棋盘/AI 交互，不直接接触 AI 线程。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from boardgames.ai import AIEngine, AIWorker, SearchStats, get_engine
from boardgames.core.game import Game
from boardgames.core.move import Move
from boardgames.core.registry import GameRegistry
from boardgames.core.result import Termination
from boardgames.core.state import State
from boardgames.settings import Settings

DEFAULT_GAME_KEY = "quoridor"


@dataclass
class Snapshot:
    """悔棋用的局面快照（不可变状态，直接存引用即可）。"""

    state: State
    move: Move | None
    player: int


class GameSession:
    """一局游戏的完整状态机。"""

    def __init__(
        self,
        settings: Settings,
        registry: GameRegistry,
        game_key: str = DEFAULT_GAME_KEY,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.game_key = game_key
        self.worker = AIWorker()
        self.rng = rng or random.Random()
        self.history: list[Snapshot] = []
        self.last_stats: SearchStats | None = None
        self.paused = False
        #: 「单步」请求：暂停状态下也允许 AI 走一子，走完仍然保持暂停
        self.stepping = False
        self._pending_move: Move | None = None
        self._pending_stats: SearchStats | None = None
        self._ready_at = 0.0
        self._thinking_since = 0.0
        self._elapsed_ms = 0.0
        self.new_game()

    # ------------------------------------------------------------------ #
    # 构建与查询
    # ------------------------------------------------------------------ #

    def _build_game(self) -> Game:
        """按当前设置实例化规则引擎。

        参数映射由各棋类自己声明（``Game.settings_map``：settings 键 → 构造参数名），
        因此这里不需要知道任何具体棋类的存在。

        早期版本这里给构造器硬传 ``size=/walls=/first_player=`` 并用
        ``except TypeError`` 兜底给不支持的棋类 —— 那个 except 会把两种完全不同的
        错误混为一谈：参数名写错、和游戏本身不读该参数。实测还导致两个问题：
        设 ``first_player=p2`` 被静默丢弃，以及返回注册表里的**共享单例**
        （跨对局状态污染）。现在改为显式声明，未声明的参数不会被误传。
        """
        cls = type(self.registry.get(self.game_key))
        kwargs: dict[str, Any] = {
            param: self.settings.get(key) for key, param in cls.settings_map.items()
        }
        if "first_player" in cls.settings_map:
            kwargs["first_player"] = self._resolve_first_player()
        return cls(**kwargs)

    def _resolve_first_player(self) -> int:
        choice = self.settings.get("first_player")
        if choice == "p1":
            return 0
        if choice == "p2":
            return 1
        return self.rng.randrange(2)

    def new_game(self) -> None:
        self.cancel_thinking()
        self.game = self._build_game()
        self.state = self.game.initial_state()
        self.result = Termination.ONGOING
        self.resigned_by: int | None = None
        # AI 自对弈默认**暂停**，由用户按"单步"或点棋盘一步步推进
        self.paused = self.mode == "eve"
        self.stepping = False
        self.history = [Snapshot(self.state, None, -1)]
        self.last_stats = None
        self._pending_move = None
        self._pending_stats = None
        self._elapsed_ms = 0.0

    # ---- 模式 ----

    @property
    def mode(self) -> str:
        return str(self.settings.get("mode"))

    def resolved_player_types(self) -> tuple[str, str]:
        """把「模式 + 双方类型」解析成每一方实际由谁操作。"""
        p1 = str(self.settings.get("p1_type"))
        p2 = str(self.settings.get("p2_type"))
        mode = self.mode
        if mode == "pvp":
            return ("human", "human")
        if mode == "pve":
            a, b = p1, p2
            if a == "human" and b == "human":
                b = "minimax"
            elif a != "human" and b != "human":
                a = "human"
            return (a, b)
        return (
            p1 if p1 != "human" else "minimax",
            p2 if p2 != "human" else "mcts",
        )

    def player_type(self, player: int) -> str:
        return self.resolved_player_types()[player]

    def is_human_turn(self) -> bool:
        return not self.is_over and self.player_type(self.state.current_player) == "human"

    def is_ai_turn(self) -> bool:
        return not self.is_over and self.player_type(self.state.current_player) != "human"

    # ---- 终局 ----

    @property
    def is_over(self) -> bool:
        return self.result is not Termination.ONGOING

    def winner(self) -> int | None:
        if self.result is Termination.RESIGN:
            return None if self.resigned_by is None else 1 - self.resigned_by
        return self.state.winner()

    def loser(self) -> int | None:
        winner = self.winner()
        return None if winner is None else 1 - winner

    def result_text(self) -> str:
        if not self.is_over:
            return ""
        meta = self.game.player_meta()
        if self.result is Termination.RESIGN and self.resigned_by is not None:
            return f"{meta[self.resigned_by].name} 认输，{meta[1 - self.resigned_by].name} 获胜"
        winner = self.winner()
        if winner is None:
            return "平局"
        return f"{meta[winner].name} 获胜！"

    # ------------------------------------------------------------------ #
    # 行棋
    # ------------------------------------------------------------------ #

    def legal_moves(self) -> list[Move]:
        if self.is_over:
            return []
        return self.game.legal_moves(self.state)

    def is_legal(self, move: Move) -> bool:
        return not self.is_over and self.game.is_legal(self.state, move)

    def play(self, move: Move, *, by: int | None = None) -> bool:
        """落子。`by` 省略时取当前行动方。"""
        if self.is_over:
            return False
        player = self.state.current_player if by is None else by
        self.state = self.game.apply(self.state, move)
        self.history.append(Snapshot(self.state, move, player))
        if self.state.is_terminal():
            self.result = Termination.WIN
        return True

    def resign(self, player: int | None = None) -> None:
        if self.is_over:
            return
        self.cancel_thinking()
        self.resigned_by = self.state.current_player if player is None else player
        self.result = Termination.RESIGN

    # ------------------------------------------------------------------ #
    # AI 编排
    # ------------------------------------------------------------------ #

    def _engine_for(self, player: int) -> AIEngine | None:
        kind = self.player_type(player)
        if kind == "human":
            return None
        return get_engine(kind)

    def cancel_thinking(self) -> None:
        self.worker.cancel()
        self._pending_move = None
        self._pending_stats = None
        self._ready_at = 0.0
        self._thinking_since = 0.0
        self.stepping = False

    def ai_allowed(self) -> bool:
        """AI 现在可以行动吗（暂停时为 False，除非用户点了「单步」）。"""
        return not self.paused or self.stepping

    def request_step(self) -> bool:
        """自对弈暂停时，让 AI 走一子；走完仍然保持暂停。"""
        if self.is_over or not self.paused or self.is_thinking():
            return False
        self.stepping = True
        return True

    def is_thinking(self) -> bool:
        """AI 是否"还在忙"。

        **必须包含 ``_pending_move``**：结果已返回、落子停顿（`ai_delay_ms`）还没过完时，
        若这里返回 False，主循环每帧都会重新调 :meth:`start_thinking` 重开一次搜索 ——
        表现就是状态栏"思考中"疯狂闪烁、而且 AI 永远不落子。
        """
        return (
            self._thinking_since > 0.0
            or self._pending_move is not None
            or self.worker.is_running()
        )

    def thinking_elapsed_ms(self) -> float:
        if self._thinking_since > 0.0:
            return (time.monotonic() - self._thinking_since) * 1000.0
        return self._elapsed_ms

    def start_thinking(self) -> None:
        """若轮到 AI 且尚未开始思考，则启动后台搜索。"""
        if self.is_over or not self.ai_allowed() or self.is_thinking():
            return
        player = self.state.current_player
        engine = self._engine_for(player)
        if engine is None:
            return
        params = self.settings.engine_params(engine.key)
        self.worker.start(self.game, self.state, player, engine, params)
        now = time.monotonic()
        self._thinking_since = now
        self._elapsed_ms = 0.0
        # 落子停顿从"开始思考"起算：AI 思考超过这个时长就立刻落子
        self._ready_at = now + max(0, int(self.settings.get("ai_delay_ms"))) / 1000.0

    def poll(self) -> Move | None:
        """每帧调用。AI 想好后由本方法落子并返回该着法（供 UI 播放动画）。"""
        if self._thinking_since > 0.0:
            result = self.worker.poll()
            if result is not None:
                self._pending_move = result.move
                self._pending_stats = result.stats
                self._elapsed_ms = (time.monotonic() - self._thinking_since) * 1000.0
                self._thinking_since = 0.0

        if self._pending_move is None or time.monotonic() < self._ready_at:
            return None

        move = self._pending_move
        self.last_stats = self._pending_stats
        self._pending_move = None
        self._pending_stats = None
        self._ready_at = 0.0
        self.stepping = False  # 单步用完就复位（paused 保持原样）
        if self.is_over or move is None or not self.game.is_legal(self.state, move):
            return None
        self.play(move)
        return move

    @property
    def pending_stats(self) -> SearchStats | None:
        return self._pending_stats

    # ------------------------------------------------------------------ #
    # 悔棋
    # ------------------------------------------------------------------ #

    def can_undo(self) -> bool:
        return len(self.history) > 1

    def undo(self) -> bool:
        """悔棋。

        * 双人同屏 / AI 自对弈：回退 1 步（自对弈顺便暂停）。
        * 人机：一直回退到「轮到人类」为止 —— 人类刚落子且 AI 已应招时是 2 步，
          AI 还在思考时是 1 步。
        """
        self.cancel_thinking()
        if len(self.history) <= 1:
            return False

        self.result = Termination.ONGOING
        self.resigned_by = None

        self._pop_once()
        if self.mode == "pve":
            guard = 0
            while len(self.history) > 1 and self.player_type(self.state.current_player) != "human":
                self._pop_once()
                guard += 1
                if guard > 4:
                    break
        if self.mode == "eve":
            self.paused = True
        return True

    def _pop_once(self) -> None:
        self.history.pop()
        self.state = self.history[-1].state
