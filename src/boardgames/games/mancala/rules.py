"""播棋（Mancala / Kalah）规则引擎。

规则要点
--------
* 2 排 × 6 列共 12 个小坑，两端各一个仓库，每坑初始 4 枚种子。
* 从己方非空小坑取出全部种子，沿自己的方向逐坑播一粒，经过己方仓库也播，
  **跳过对手仓库**。
* 最后一粒落在**己方仓库** → **再走一手**（额外回合）。
* 最后一粒落在**己方空坑** → 连同正对面对手坑里的种子一起收进己方仓库（捕获）。
* 某方小坑全空 → 对手收走自己坑里剩余种子，仓库多者胜。
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import replace

from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.mancala.heuristic import evaluate as _evaluate_static
from boardgames.games.mancala.move import SowMove
from boardgames.games.mancala.state import (
    DEFAULT_PITS,
    DEFAULT_SEEDS,
    MancalaState,
    initial_state,
    sow_path,
)


class MancalaGame(Game[MancalaState, Move]):
    """播棋。"""

    key = "mancala"
    display_name = "播棋"

    settings_map = {
        "mancala_pits": "pits_per_side",
        "mancala_seeds": "seeds_per_pit",
    }

    tagline = "Mancala · 播种棋"
    summary = "轮流从己方坑取种子逐坑播种，落到己方仓库可再走，仓库多者胜。"
    goal = "终局时自己仓库里的种子更多"
    rules = (
        "盘面是 2 排 × 6 列共 12 个小坑，两端各有一个大坑（仓库）",
        "开局每个小坑放 4 枚种子，仓库为空",
        "轮到谁，就从**自己一侧**任意一个非空小坑取出全部种子",
        "沿自己的方向逐坑播一粒（逆时针绕一圈），经过己方仓库时也播一粒，跳过对手仓库",
        "最后一粒落在己方仓库 → 立即**再走一手**",
        "最后一粒落在己方空坑 → 这一粒连同正对面对手坑里的种子一起收进己方仓库",
        "某方所有小坑清空时结束，对方收走自己坑里剩余种子，仓库种子多者胜",
    )
    howto = (
        "鼠标点己方一侧某个小坑播种",
        "悬停会高亮这个坑及播种的落点预览",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "最后一粒落在己方仓库能白赚一手，开局优先找这种坑",
        "留一枚种子在靠近己方仓库的坑里，方便触发捕获",
        "别让一侧坑彻底空掉，否则会提前触发终局、便宜了对手",
    )
    icon = "mancala"

    def __init__(
        self,
        pits_per_side: int = DEFAULT_PITS,
        seeds_per_pit: int = DEFAULT_SEEDS,
        *,
        first_player: int = 0,
    ) -> None:
        self.pits_per_side = int(pits_per_side)
        self.seeds_per_pit = int(seeds_per_pit)
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

    def initial_state(self, first_player: int | None = None) -> MancalaState:
        return initial_state(
            self.pits_per_side,
            self.seeds_per_pit,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 着法生成
    # ------------------------------------------------------------------ #

    def legal_moves(self, state: MancalaState, options: SearchOptions | None = None) -> list[SowMove]:
        """合法着法 = 己方所有非空小坑。分支最多 6，不裁剪。"""
        if state.is_terminal():
            return []
        player = state.current
        moves = [SowMove(pit, player) for pit in state.own_pits(player)]
        if options is not None and options.order:
            moves.sort(key=lambda m: self._order_key(state, m), reverse=True)
        return moves

    def _order_key(self, state: MancalaState, move: SowMove) -> float:
        """排序：优先能额外回合 / 能捕获 / 落点靠后的坑。"""
        player = state.current
        seeds = state.pits[move.pit]
        path = sow_path(state.pits_per_side, move.pit, player, seeds)
        last_idx, is_store = path[-1]
        score = 0.0
        if is_store:
            score += 100.0
        else:
            # 落在己方空坑 = 捕获
            if state.pits[last_idx] == 0 and last_idx in state.pit_range(player):
                opp = state.opposite(last_idx)
                score += 50.0 + state.pits[opp] * 5.0
        return score

    def is_legal(self, state: MancalaState, move: Move) -> bool:
        if not isinstance(move, SowMove):
            return False
        if state.is_terminal() or move.player != state.current:
            return False
        return move.pit in state.own_pits(state.current)

    def apply(self, state: MancalaState, move: Move) -> MancalaState:
        """执行播种。返回**新**对象。"""
        if not self.is_legal(state, move):
            raise ValueError(f"非法着法: {move}")

        player = state.current
        p = state.pits_per_side
        pits = list(state.pits)
        stores = list(state.stores)

        # 取出种子
        seeds = pits[move.pit]
        pits[move.pit] = 0

        # 播种
        path = sow_path(p, move.pit, player, seeds)
        for idx, is_store in path:
            if is_store:
                stores[idx] += 1
            else:
                pits[idx] += 1

        last_idx, last_is_store = path[-1]
        extra_turn = False
        if last_is_store:
            # 落己方仓库 → 额外回合
            extra_turn = True
        else:
            # 落己方空坑（播种前为空，且现在只有这一粒）→ 捕获对面
            if last_idx in state.pit_range(player) and pits[last_idx] == 1:
                opp = state.opposite(last_idx)
                captured = pits[opp]
                pits[opp] = 0
                pits[last_idx] = 0
                stores[player] += captured + 1
                # 注意：last_idx 现在被清空，那一粒也进仓库

        # 终局判定：某方小坑全空
        winner = state.winner_player
        over = state.over
        if winner is None:
            # 检查当前玩家（或对手）是否全空
            for side_player in (player, 1 - player):
                if all(pits[i] == 0 for i in state.pit_range(side_player)):
                    # 对手收走剩余种子
                    other = 1 - side_player
                    for i in state.pit_range(other):
                        stores[other] += pits[i]
                        pits[i] = 0
                    over = True
                    if stores[0] != stores[1]:
                        winner = 0 if stores[0] > stores[1] else 1
                    break

        nxt = player if extra_turn else 1 - player

        return replace(
            state,
            pits=tuple(pits),
            stores=tuple(stores),
            current=nxt,
            ply=state.ply + 1,
            winner_player=winner,
            over=over,
        )

    # ------------------------------------------------------------------ #
    # 评估与模拟
    # ------------------------------------------------------------------ #

    def evaluate(
        self, state: MancalaState, player: int, weights: Mapping[str, float] | None = None
    ) -> float:
        return _evaluate_static(state, player, weights)

    def rollout_move(
        self,
        state: MancalaState,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> SowMove:
        """rollout 策略：优先额外回合 / 捕获，否则随机。

        收敛性：种子总数守恒，且每次播种都会消耗某个坑的种子、把至少一粒送进
        仓库或对手坑；MCTS 的 rollout_depth_cap 兜底防振荡。
        """
        moves = self.legal_moves(state)
        if not moves:
            raise RuntimeError("局面已终局，不该再请求 rollout 着法")

        # 能额外回合的优先
        extra = [m for m in moves if self._order_key(state, m) >= 100.0]
        if extra and rng.random() < 0.7:
            return rng.choice(extra)

        # 能捕获的次优先
        capture = [m for m in moves if 50.0 <= self._order_key(state, m) < 100.0]
        if capture and rng.random() < 0.6:
            return rng.choice(capture)

        return rng.choice(moves)

    # ------------------------------------------------------------------ #
    # 提示
    # ------------------------------------------------------------------ #

    def describe_state(self, state: MancalaState) -> str:
        if state.winner_player is not None:
            return f"{self.player_meta()[state.winner_player].name}仓库更多"
        return f"{self.player_meta()[state.current].name}播种"

    def move_hints(self, state: MancalaState) -> dict[str, object]:
        return {"stores": state.stores, "pits": state.pits}


DEFAULT_OPTIONS = SearchOptions()
__all__ = ["MancalaGame", "MancalaState", "SowMove", "DEFAULT_OPTIONS"]
