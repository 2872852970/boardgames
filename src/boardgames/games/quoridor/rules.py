"""Quoridor 规则引擎。"""

from __future__ import annotations

import random
from collections.abc import Mapping

from boardgames.core.game import FULL_SEARCH, Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.quoridor import geometry as geo
from boardgames.games.quoridor.heuristic import (
    DEFAULT_WEIGHTS,
    merged_weights,
)
from boardgames.games.quoridor.heuristic import (
    evaluate as _evaluate_static,
)
from boardgames.games.quoridor.move import PawnMove, WallMove
from boardgames.games.quoridor.state import (
    DEFAULT_SIZE,
    DEFAULT_WALLS,
    QuoridorState,
    initial_state,
)

_INF_DIST = 10 ** 6


class QuoridorGame(Game[QuoridorState, Move]):
    """步步为营（墙棋）。

    规则要点：
    * 每回合二选一：走子一格（含跳跃）或放一面墙。
    * 墙长 2 格，禁止同向重叠、禁止同锚点交叉；端点相接的 L/T 形合法。
    * 放墙后**双方**都必须仍能到达各自目标行，否则该墙非法。
    """

    key = "quoridor"
    display_name = "步步为营"

    settings_map = {
        "board_size": "size",
        "walls_per_player": "walls",
    }

    tagline = "Quoridor · 墙棋"
    summary = "每人带十面墙抢先抵达对面底线，墙会挡住对手的去路。"
    goal = "让自己的棋子先走到对面底线"
    rules = (
        "双方各执一子，从己方底边中央出发，先抵达对面底线者胜",
        "每回合二选一：把己子移动一格（上下左右），或放一面墙",
        "墙长两格、正好挡住两条相邻边；不能与已有墙重叠，也不许交叉成十字",
        "端点相接的 L / T 形是合法的，只有「十字交叉」被禁止",
        "任何一面墙都不得把任意一方的通路完全封死 —— 总得留一条路",
        "双方棋子正面相邻时可以跳过对方，直接落到它正后方那一格",
        "若正后方被墙或棋盘边界挡住，可改为斜跳到它的左前或右前",
        "墙用完就只能走子了，所以别太早把墙浪费掉",
    )
    howto = (
        "鼠标移到相邻格上的高亮圆点，点击走子",
        "鼠标移到两格之间的边上会预览墙，点击落墙",
        "右键（或 W）进入 / 退出放墙模式，V 键换横墙竖墙，Esc 也能退",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "放墙的价值在于让对手多绕路，不是把自己也堵死",
        "过深的搜索会关掉放墙分支（分支太大），想看 AI 放墙就把深度调小",
    )
    icon = "board"

    def __init__(
        self,
        size: int = DEFAULT_SIZE,
        walls: int = DEFAULT_WALLS,
        *,
        first_player: int = 0,
        jump_diag_checks_wall: bool = True,
        allow_wall_crossing: bool = False,
    ) -> None:
        self.size = size
        self.walls = walls
        self.first_player = first_player
        #: 斜跳时是否检查 ``对手 → 斜向目标`` 这条边是否被墙阻断。
        self.jump_diag_checks_wall = jump_diag_checks_wall
        #: 是否允许横竖墙在同一锚点交叉成"十"字（默认严格禁止）。
        self.allow_wall_crossing = allow_wall_crossing

    # ------------------------------------------------------------------ #
    # 基本信息
    # ------------------------------------------------------------------ #

    def player_count(self) -> int:
        return 2

    def player_meta(self) -> list[PlayerMeta]:
        return [
            PlayerMeta(name="玩家 1", color=(240, 185, 90)),   # 琥珀
            PlayerMeta(name="玩家 2", color=(91, 141, 239)),   # 蓝
        ]

    def initial_state(self, first_player: int | None = None) -> QuoridorState:
        return initial_state(
            self.size,
            self.walls,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 走子生成
    # ------------------------------------------------------------------ #

    def pawn_moves_for(self, state: QuoridorState, player: int) -> list[PawnMove]:
        """生成 ``player`` 的合法走子（含普通移动、直跳、斜跳）。"""
        size, h, v = state.size, state.h_mask, state.v_mask
        pos = state.pawns[player]
        other = state.pawns[1 - player]
        occupied = {other}
        out: list[PawnMove] = []
        for dx, dy in geo.ORTHO:
            nx, ny = pos[0] + dx, pos[1] + dy
            if not geo.in_board(size, nx, ny):
                continue
            if not geo.can_step(size, h, v, pos, (nx, ny)):
                continue
            if (nx, ny) not in occupied:
                out.append(PawnMove(pos, (nx, ny)))
                continue

            # 面对对方棋子 —— 尝试跳跃
            sx, sy = nx + dx, ny + dy
            if geo.in_board(size, sx, sy) and (sx, sy) not in occupied and geo.can_step(
                size, h, v, other, (sx, sy)
            ):
                # 正后方可落 → 直跳（此时不再生成斜跳，二者互斥）
                out.append(PawnMove(pos, (sx, sy)))
                continue

            # 正后方被墙/边界阻挡 → 尝试斜跳，两个垂直方向各自独立判定
            for px, py in ((-dy, dx), (dy, -dx)):
                tx, ty = nx + px, ny + py
                if not geo.in_board(size, tx, ty):
                    continue
                if (tx, ty) == pos or (tx, ty) in occupied:
                    continue
                if self.jump_diag_checks_wall and not geo.can_step(
                    size, h, v, other, (tx, ty)
                ):
                    continue
                out.append(PawnMove(pos, (tx, ty)))
        return out

    # ------------------------------------------------------------------ #
    # 放墙：合法性 / 价值
    # ------------------------------------------------------------------ #

    def _add_wall_masks(self, state: QuoridorState, wall: geo.Wall) -> tuple[int, int]:
        orient, ax, ay = wall
        bit = geo.anchor_bit(state.size, ax, ay)
        if orient == geo.HORIZONTAL:
            return state.h_mask | bit, state.v_mask
        return state.h_mask, state.v_mask | bit

    def _path_info(
        self, state: QuoridorState, player: int
    ) -> tuple[list[geo.Pos], frozenset[geo.EdgeKey]]:
        """返回该玩家的一条最短路径（格子序列）与它经过的边集合。"""
        path = geo.shortest_path_cells(
            state.size, state.h_mask, state.v_mask, state.pawns[player], state.goal_row(player)
        )
        if not path:
            return [], frozenset()
        return path, geo.path_edge_keys(path)

    def _validate_wall(
        self,
        state: QuoridorState,
        player: int,
        wall: geo.Wall,
        *,
        base_opp_dist: float | None = None,
        opp_edges: frozenset[geo.EdgeKey] | None = None,
        my_edges: frozenset[geo.EdgeKey] | None = None,
    ) -> float | None:
        """校验放墙；合法则返回"对手最短路径的增量"，非法返回 ``None``。

        合并了全部几何校验与连通性校验，避免在候选排序时重复计算。

        ``opp_edges`` / ``my_edges`` 是双方各自最短路径的**边集合**，用来跳过 BFS：

        * 该墙不阻断我当前最短路径上的任何边 → 我必然仍连通，无需 BFS；
        * 该墙不阻断对手当前最短路径上的任何边 → 对手距离不变（增量恒为 0）。

        这两个剪枝把放墙校验的开销砍掉了大半（``all_legal_walls`` 从 ~10ms 降到 ~2ms）。
        """
        if state.walls_left[player] <= 0:
            return None
        if not geo.in_anchor_grid(state.size, wall[1], wall[2]):
            return None
        if geo.wall_overlaps(state.size, state.h_mask, state.v_mask, wall):
            return None
        if not self.allow_wall_crossing and geo.wall_crosses(
            state.h_mask, state.v_mask, state.size, wall
        ):
            return None

        size = state.size
        opp = 1 - player
        keys = geo.wall_edge_keys(wall)
        touches_me = my_edges is None or any(k in my_edges for k in keys)
        touches_opp = opp_edges is None or any(k in opp_edges for k in keys)

        h2, v2 = self._add_wall_masks(state, wall)

        if touches_me and geo.shortest_path(
            size, h2, v2, state.pawns[player], state.goal_row(player)
        ) is None:
            return None  # 把自己的路也封死了 → 非法

        if not touches_opp:
            return 0.0  # 对手路径未受影响

        d_opp = geo.shortest_path(size, h2, v2, state.pawns[opp], state.goal_row(opp))
        if d_opp is None:
            return None  # 封死对手 → 非法
        if base_opp_dist is None:
            return 0.0
        return float(d_opp) - float(base_opp_dist)

    def is_wall_legal(self, state: QuoridorState, player: int, wall: geo.Wall) -> bool:
        return self._validate_wall(state, player, wall) is not None

    def all_legal_walls(self, state: QuoridorState, player: int) -> list[WallMove]:
        """全部合法墙位（UI / 完整着法列表用）。"""
        if state.walls_left[player] <= 0:
            return []
        size = state.size
        w = size - 1
        opp = 1 - player
        opp_path, opp_edges = self._path_info(state, opp)
        _my_path, my_edges = self._path_info(state, player)
        base_opp_dist = float(len(opp_path) - 1) if opp_path else float(size * size)

        out: list[WallMove] = []
        for ay in range(w):
            for ax in range(w):
                for orient in (geo.HORIZONTAL, geo.VERTICAL):
                    if (
                        self._validate_wall(
                            state,
                            player,
                            (orient, ax, ay),
                            base_opp_dist=base_opp_dist,
                            opp_edges=opp_edges,
                            my_edges=my_edges,
                        )
                        is not None
                    ):
                        out.append(WallMove(orient, ax, ay))
        return out

    def _anchors_from_path(self, size: int, path: list[geo.Pos]) -> list[geo.Wall]:
        cands: set[geo.Wall] = set()
        for a, b in zip(path, path[1:], strict=False):
            cands.update(geo.anchors_blocking_step(size, a, b))
        return sorted(cands)

    def geometric_wall_candidates(self, state: QuoridorState, player: int) -> list[geo.Wall]:
        """**只按几何**挑出"值得考虑"的墙位（不做 BFS 校验，因此非常便宜）。

        取**对手**最短路径上每一步的相邻边，找出能阻断这些边的锚点。
        阻断自己道路的墙对自己只有坏处，因此不列入候选。
        """
        opp = 1 - player
        path = geo.shortest_path_cells(
            state.size, state.h_mask, state.v_mask, state.pawns[opp], state.goal_row(opp)
        )
        if not path:
            return []
        return self._anchors_from_path(state.size, path)

    def candidate_walls(self, state: QuoridorState, player: int, limit: int) -> list[WallMove]:
        """搜索用墙候选：几何候选 → 合法性校验 → 按收益降序 → 截断。

        这是让 Minimax/MCTS 在巨大分支因子下仍然可用的关键。
        """
        if state.walls_left[player] <= 0:
            return []
        size = state.size
        opp = 1 - player
        opp_path, opp_edges = self._path_info(state, opp)
        _my_path, my_edges = self._path_info(state, player)
        base_opp_dist = float(len(opp_path) - 1) if opp_path else float(size * size)

        scored: list[tuple[float, geo.Wall]] = []
        for wall in self._anchors_from_path(size, opp_path):
            gain = self._validate_wall(
                state,
                player,
                wall,
                base_opp_dist=base_opp_dist,
                opp_edges=opp_edges,
                my_edges=my_edges,
            )
            if gain is None:
                continue
            scored.append((gain, wall))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if limit and limit > 0:
            scored = scored[:limit]
        return [WallMove(*wall) for _, wall in scored]

    def sample_legal_wall(
        self, state: QuoridorState, player: int, rng: random.Random, attempts: int = 4
    ) -> WallMove | None:
        """给 rollout 用的**廉价**放墙采样：只试少数几个候选就放弃。"""
        if state.walls_left[player] <= 0:
            return None
        cands = self.geometric_wall_candidates(state, player)
        if not cands:
            return None
        rng.shuffle(cands)
        for wall in cands[:attempts]:
            if self.is_wall_legal(state, player, wall):
                return WallMove(*wall)
        return None

    # ------------------------------------------------------------------ #
    # Game 接口
    # ------------------------------------------------------------------ #

    def legal_moves(
        self, state: QuoridorState, options: SearchOptions | None = None
    ) -> list[Move]:
        if state.is_terminal():
            return []
        player = state.current
        pawn_moves = self.pawn_moves_for(state, player)

        want_walls = (
            state.walls_left[player] > 0
            and (options is None or options.include_walls)
        )
        if not want_walls:
            if options is not None and options.order:
                return list(self._order_pawn_moves(state, player, pawn_moves))
            return list(pawn_moves)

        if options is None:
            return list(pawn_moves) + self.all_legal_walls(state, player)

        walls = self.candidate_walls(state, player, options.max_branch)
        if options.order:
            return list(self._order_pawn_moves(state, player, pawn_moves)) + list(walls)
        return list(pawn_moves) + list(walls)

    def _order_pawn_moves(
        self, state: QuoridorState, player: int, moves: list[PawnMove]
    ) -> list[PawnMove]:
        """走子排序：让己方最短路径变得越短越靠前（直接获胜的必然排第一）。"""

        def key(move: PawnMove) -> int:
            pawns = list(state.pawns)
            pawns[player] = move.dst
            d = geo.shortest_path(
                state.size,
                state.h_mask,
                state.v_mask,
                move.dst,
                state.goal_row(player),
            )
            return _INF_DIST if d is None else d

        return sorted(moves, key=key)

    def is_legal(self, state: QuoridorState, move: Move) -> bool:
        if state.is_terminal():
            return False
        player = state.current
        if isinstance(move, PawnMove):
            if move.src != state.pawns[player]:
                return False
            return move in self.pawn_moves_for(state, player)
        if isinstance(move, WallMove):
            return self.is_wall_legal(state, player, move.wall)
        return False

    def apply(self, state: QuoridorState, move: Move) -> QuoridorState:
        player = state.current
        nxt = 1 - player
        if isinstance(move, PawnMove):
            pawns = list(state.pawns)
            pawns[player] = move.dst
            return QuoridorState(
                size=state.size,
                pawns=(pawns[0], pawns[1]),
                walls_left=state.walls_left,
                h_mask=state.h_mask,
                v_mask=state.v_mask,
                current=nxt,
                ply=state.ply + 1,
            )
        assert isinstance(move, WallMove)
        h2, v2 = self._add_wall_masks(state, move.wall)
        walls_left = list(state.walls_left)
        walls_left[player] -= 1
        return QuoridorState(
            size=state.size,
            pawns=state.pawns,
            walls_left=(walls_left[0], walls_left[1]),
            h_mask=h2,
            v_mask=v2,
            current=nxt,
            ply=state.ply + 1,
        )

    def evaluate(
        self,
        state: QuoridorState,
        player: int,
        weights: Mapping[str, float] | None = None,
    ) -> float:
        counts = (
            len(self.pawn_moves_for(state, player)),
            len(self.pawn_moves_for(state, 1 - player)),
        )
        return _evaluate_static(state, player, weights, pawn_move_counts=counts)

    # ------------------------------------------------------------------ #
    # MCTS rollout 策略
    # ------------------------------------------------------------------ #

    def rollout_move(
        self,
        state: QuoridorState,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> Move:
        """默认 rollout 策略：小概率随机放墙，否则沿目标距离场前进。

        用距离场而不是"曼哈顿距离"来选步，是为了**保证单调推进**：
        只要距离能变小就一定变小，rollout 不会来回振荡，棋局必然收敛。
        """
        player = state.current
        p_wall = merged_weights(weights).get("p_wall", DEFAULT_WEIGHTS["p_wall"])

        if state.walls_left[player] > 0 and rng.random() < p_wall:
            wall = self.sample_legal_wall(state, player, rng, attempts=2)
            if wall is not None:
                return wall

        pawn_moves = self.pawn_moves_for(state, player)
        if not pawn_moves:
            wall = self.sample_legal_wall(state, player, rng, attempts=8)
            return wall if wall is not None else self._fallback_move(state)

        size = state.size
        field = geo.distance_field(size, state.h_mask, state.v_mask, state.goal_row(player))

        def rank(move: PawnMove) -> int:
            value = field[move.dst[1] * size + move.dst[0]]
            return _INF_DIST if value < 0 else value

        best = min(rank(move) for move in pawn_moves)
        best_moves = [move for move in pawn_moves if rank(move) == best]
        return rng.choice(best_moves)

    def _fallback_move(self, state: QuoridorState) -> Move:
        player = state.current
        moves = self.pawn_moves_for(state, player)
        if moves:
            return moves[0]
        walls = self.all_legal_walls(state, player)
        if walls:
            return walls[0]
        raise RuntimeError("无合法着法（局面不合法）")

    # ------------------------------------------------------------------ #
    # UI 辅助
    # ------------------------------------------------------------------ #

    def describe_state(self, state: QuoridorState) -> str:
        p = state.current
        return f"{self.player_meta()[p].name} 行动 · 剩余墙 {state.walls_of(p)}"


#: 默认（全量）选项，便于外部引用。
DEFAULT_OPTIONS = FULL_SEARCH
