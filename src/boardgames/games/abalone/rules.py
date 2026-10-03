"""大力士棋（Abalone）规则引擎。

规则要点
--------
* 六边形棋盘 61 格，双方各 14 子，先把对手 **6 子** 挤出盘外即胜。
* 每回合把 **1 / 2 / 3 枚连成一线**的己方棋子移动一格：
  * **in-line（直推）**：沿这组棋子所在轴的前后方向；
  * **broadside（横移）**：平行于这排棋子的侧向，全部目标格必须为空。
* **只有 in-line 能推挤**，且必须 **以多推少**：2 推 1、3 推 1、3 推 2。
  1 推 1 / 2 推 2 / 3 推 3 是对峙（standoff），谁也推不动；单枚棋子也不能推。
* 被推的对手串**之后那一格必须为空或出界** —— 出界就是被挤出盘外。那一格若被
  **任何一方**占着（包括己方棋子），就形成"两侧夹住"，推不动。
* 横移**不能**推挤。

搜索裁剪
--------
分支因子开局就有 44~80、中局峰值接近 100，所以 :class:`SearchOptions.max_branch`
是大力士棋**唯一真正用得上**的裁剪开关。

``include_walls`` / ``include_special`` 一律**忽略** —— ``include_walls`` 是
步步为营的语义（minimax 会按 ``ply < wall_depth`` 逐层关掉它），若把它当成
"裁剪着法"，深度 ≥2 的节点就几乎没着法了，棋力会直接崩掉（四子棋踩过同一口井，
见 ``connect4/rules.py``）。
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import replace

from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.abalone.geometry import (
    CELLS,
    CENTER_SCORE,
    DIRECTIONS,
    INDEX,
    LINES_INDEX,
    NEIGHBORS,
    RING,
    Pos,
    group_axis,
)
from boardgames.games.abalone.heuristic import evaluate as _evaluate_static
from boardgames.games.abalone.layouts import (
    ABALONE_SETUPS,
    DEFAULT_SETUP,
    WIN_OUT,
)
from boardgames.games.abalone.move import AbaloneMove
from boardgames.games.abalone.state import EMPTY, AbaloneState, initial_state


def _plan(
    cells: tuple[int, ...],
    group: tuple[int, ...],
    axis: int,
    direction: int,
    me: int,
) -> tuple[tuple[int, ...], int | None] | None:
    """判定一次移动能否成立，返回 ``(被推动的下标, 被挤出盘外的下标)``。

    两个返回值都是**棋盘下标**；非法返回 ``None``。
    """
    opp = 3 - me

    if direction % 3 == axis:
        # ---- in-line：可以推挤 ----
        members = set(group)
        head = -1
        for cell in group:
            if NEIGHBORS[cell][direction] not in members:
                head = cell
                break
        nxt = NEIGHBORS[head][direction]
        if nxt < 0:
            return None  # 朝着盘外推自己，没有意义
        value = cells[nxt]
        if value == EMPTY:
            return ((), None)
        if value == me:
            return None  # 不能推己方棋子

        # 数前方连续的对手子（最多 3 枚 —— 再多必然推不动）
        pushed: list[int] = []
        probe = nxt
        while len(pushed) < 3 and probe >= 0 and cells[probe] == opp:
            pushed.append(probe)
            probe = NEIGHBORS[probe][direction]
        if not pushed or len(pushed) >= len(group):
            return None  # 以多推少：1v1 / 2v2 / 3v3 都是对峙，单子也推不动
        if probe < 0:
            # 对手串正好顶在盘边 -> 最后一枚被挤出盘外
            return (tuple(pushed[:-1]), pushed[-1])
        if cells[probe] != EMPTY:
            return None  # 后面堵着东西（敌我都算）-> 两侧夹住，推不动
        return (tuple(pushed), None)

    # ---- broadside：所有目标格必须在盘且为空（横移不能推挤）----
    for cell in group:
        nxt = NEIGHBORS[cell][direction]
        if nxt < 0 or cells[nxt] != EMPTY:
            return None
    return ((), None)


def _dest_index(pos: Pos, direction: int) -> int | None:
    """``pos`` 沿 ``direction`` 前进一格的棋盘下标；出界返回 ``None``。"""
    dq, dr = DIRECTIONS[direction]
    return INDEX.get((pos[0] + dq, pos[1] + dr))


class AbaloneGame(Game[AbaloneState, Move]):
    """大力士棋。"""

    key = "abalone"
    display_name = "大力士棋"

    settings_map = {
        "abalone_setup": "setup",
        "first_player": "first_player",
    }

    tagline = "Abalone · 推挤棋"
    summary = "六边形 61 格，双方各 14 子；1~3 连子可直推或横移，把对手 6 子挤出盘外即胜。"
    goal = "先把对方 6 枚弹子挤出棋盘"
    rules = (
        "盘面是边长 5 的六边形共 61 格，双方各 14 枚弹子",
        "每回合移动 1~3 枚连成一直线的己方弹子：沿这条线前进一格，或整排侧移一格",
        "六边形棋盘上每个方向都有六个朝向，直线前进与侧移各算一种",
        "以多推少：2 推 1、3 推 1、3 推 2；数量相同或更少时推不动",
        "被推的一方后方必须是空格或已经在盘外，否则这一推不成立",
        "推挤不改变相对顺序：被推的弹子沿同一条线被顶出去",
        "只能推对方的弹子，推不了自己人",
        "被挤出盘外的弹子立即出局，先挤掉对方 6 枚者胜",
    )
    howto = (
        "点己方一枚弹子选中，再点虚线目标格走子",
        "再点同一条直线上的己方弹子可以把这组扩到 2~3 枚；再点一次已选中的弹子则缩小",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "贴着盘边的弹子最危险 —— 它离出界只差一推",
        "把己方弹子连成团，对手就凑不出「以多推少」的必要人数",
    )
    icon = "hex"

    def __init__(self, setup: str = DEFAULT_SETUP, *, first_player: int = 0) -> None:
        if setup not in ABALONE_SETUPS:
            raise ValueError(f"未知的起始布局: {setup!r}")
        self.setup = setup
        self.first_player = first_player

    # ------------------------------------------------------------------ #
    # 基本信息
    # ------------------------------------------------------------------ #

    def player_count(self) -> int:
        return 2

    def player_meta(self) -> list[PlayerMeta]:
        # 颜色用 RGB 字面量而不是 ui.theme.P0/P1 —— 本包不得依赖 pygame 侧模块。
        # 这两个值与 theme.PLAYER_COLORS 一致，改主题时要同步。
        return [
            PlayerMeta(name="玩家 1", color=(240, 185, 90)),   # 琥珀（黑方 / 先手）
            PlayerMeta(name="玩家 2", color=(91, 141, 239)),    # 蓝
        ]

    def initial_state(self, first_player: int | None = None) -> AbaloneState:
        return initial_state(
            self.setup,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 着法生成
    # ------------------------------------------------------------------ #

    def legal_moves(self, state: AbaloneState, options: SearchOptions | None = None) -> list[AbaloneMove]:
        """当前玩家的全部合法着法。

        单子与 2/3 连子**分开生成**：LINES 表里只有长度 2/3 的片段，单子单独
        扫一遍六个方向 —— 否则"每组 × 3 条轴"会把单子重复生成三遍。
        """
        if state.is_terminal():
            return []
        me = state.current + 1
        cells = state.cells
        player = state.current
        moves: list[AbaloneMove] = []

        # ---- 单子：六个方向里目标格为空即可 ----
        for index, value in enumerate(cells):
            if value != me:
                continue
            pos = CELLS[index]
            for direction in range(6):
                nxt = NEIGHBORS[index][direction]
                if nxt >= 0 and cells[nxt] == EMPTY:
                    moves.append(AbaloneMove(player, (pos,), direction))

        # ---- 2 / 3 连子：直推（含推挤）或横移 ----
        for group, axis in LINES_INDEX:
            if any(cells[k] != me for k in group):
                continue
            for direction in range(6):
                plan = _plan(cells, group, axis, direction, me)
                if plan is None:
                    continue
                pushed, ejected = plan
                moves.append(
                    AbaloneMove(
                        player,
                        tuple(sorted(CELLS[k] for k in group)),
                        direction,
                        pushed=tuple(CELLS[k] for k in pushed),
                        ejected=None if ejected is None else CELLS[ejected],
                    )
                )

        if options is not None:
            cap = options.max_branch if options.max_branch and options.max_branch > 0 else 0
            # **截断隐含排序**：不开 order 又开了 max_branch 时，被裁掉的是生成顺序里
            # 靠后的那批 —— 而生成顺序是"先单子、后 LINES 表"，等于把推挤类着法
            # （恰恰是最该留的）系统性砍光。MCTS 传的就是 ``order=False``，实测
            # 会连"白送一枚挤出"都看不到。所以这里只要会截断就先按 _order_key 排。
            if options.order or 0 < cap < len(moves):
                moves.sort(key=_order_key, reverse=True)
            if cap:
                moves = moves[:cap]
        return moves

    def is_legal(self, state: AbaloneState, move: Move) -> bool:
        if not isinstance(move, AbaloneMove):
            return False
        if state.is_terminal() or move.player != state.current:
            return False
        if not 1 <= len(move.cells) <= 3 or not 0 <= move.direction < 6:
            return False
        me = state.current + 1
        group: list[int] = []
        for pos in move.cells:
            index = INDEX.get(pos)
            if index is None or state.cells[index] != me:
                return False
            group.append(index)
        axis = group_axis(tuple(group))
        if len(group) > 1 and axis < 0:
            return False
        # 一律**重算**，不去比对 legal_moves 的缓存列表：pushed / ejected 是
        # compare=False 的附带字段，手搭的着法可能没带，重算才稳。
        return _plan(state.cells, tuple(group), axis, move.direction, me) is not None

    def apply(self, state: AbaloneState, move: Move) -> AbaloneState:
        """执行一步。返回**新**对象，不改入参。"""
        if not self.is_legal(state, move):
            raise ValueError(f"非法着法: {move}")

        player = state.current
        me = player + 1
        opp = 3 - me
        cells = list(state.cells)
        group = tuple(INDEX[pos] for pos in move.cells)
        axis = group_axis(group)
        plan = _plan(state.cells, group, axis, move.direction, me)
        # is_legal 已经判过合法性，这里必然有结果
        pushed, ejected = plan if plan is not None else ((), None)

        for index in group:
            cells[index] = EMPTY
        for index in pushed:
            cells[index] = EMPTY
        for index in group:
            cells[NEIGHBORS[index][move.direction]] = me
        for index in pushed:
            cells[NEIGHBORS[index][move.direction]] = opp

        out = state.out
        if ejected is not None:
            out = (out[0] + 1, out[1]) if player == 0 else (out[0], out[1] + 1)

        winner = state.winner_player
        if winner is None and out[player] >= WIN_OUT:
            winner = player

        return replace(
            state,
            cells=tuple(cells),
            out=out,
            current=1 - player,
            ply=state.ply + 1,
            winner_player=winner,
        )

    # ------------------------------------------------------------------ #
    # 评估与模拟
    # ------------------------------------------------------------------ #

    def evaluate(
        self, state: AbaloneState, player: int, weights: Mapping[str, float] | None = None
    ) -> float:
        return _evaluate_static(state, player, weights)

    def rollout_move(
        self,
        state: AbaloneState,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> AbaloneMove:
        """MCTS 的 rollout 策略：**强烈偏向推挤**。

        纯随机 rollout 走 300 手双方各只挤出 1~2 子，局面几乎不动 —— MCTS 的
        价值信号就全指望评估函数了。改成"90% 直接取能挤出盘外的着法"之后，
        300~400 手内就能稳定分出胜负。

        振荡不用特别防：MCTS 有 ``rollout_depth_cap`` 兜底，且大力士棋的
        ``is_terminal`` 只看挤出数，最差也是被 cap 截断。
        """
        moves = self.legal_moves(state)
        if not moves:
            raise RuntimeError("局面已终局，不该再请求 rollout 着法")

        ejections = [m for m in moves if m.ejected is not None]
        if ejections and rng.random() < 0.9:
            return rng.choice(ejections)
        pushes = [m for m in moves if m.pushed]
        if pushes and rng.random() < 0.35:
            return rng.choice(pushes)

        scored = sorted(moves, key=_rollout_score, reverse=True)
        top = scored[: max(1, len(scored) // 5)]
        return rng.choice(top)

    # ------------------------------------------------------------------ #
    # 提示
    # ------------------------------------------------------------------ #

    def describe_state(self, state: AbaloneState) -> str:
        if state.winner_player is not None:
            return f"{self.player_meta()[state.winner_player].name}挤出对方 6 子"
        return f"{self.player_meta()[state.current].name}走子"

    def move_hints(self, state: AbaloneState) -> dict[str, object]:
        return {"count": len(self.legal_moves(state))}


def _order_key(move: AbaloneMove) -> float:
    """着法排序（``SearchOptions.order``）：能挤出 > 能推动 > 大组 > 靠中心。"""
    score = 300.0 * (move.ejected is not None) + 60.0 * len(move.pushed) + 20.0 * len(move.cells)
    for pos in move.cells:
        dest = _dest_index(pos, move.direction)
        score += CENTER_SCORE[dest] if dest is not None else CENTER_SCORE[INDEX[pos]]
    return score


def _rollout_score(move: AbaloneMove) -> float:
    """rollout 排序：己方往中心靠、对手往边上挤。"""
    score = 0.0
    for pos in move.cells:
        dest = _dest_index(pos, move.direction)
        if dest is not None:
            score -= RING[dest]
    for pos in move.pushed:
        dest = _dest_index(pos, move.direction)
        if dest is not None:
            score += 0.6 * RING[dest]
    return score


DEFAULT_OPTIONS = SearchOptions()
__all__ = ["AbaloneGame", "AbaloneState", "AbaloneMove", "WIN_OUT", "DEFAULT_OPTIONS", "_plan"]
