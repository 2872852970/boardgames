"""昆虫棋（Hive）规则引擎。

规则要点
--------
* **无边界棋盘** —— 棋子自己就是棋盘，蜂巢的形状就是当前的棋盘。
* 每方 11 枚（蜂后 1 / 甲虫 2 / 蚱蜢 3 / 蜘蛛 2 / 兵蚁 3），启用扩展后 14 枚。
* 每回合**二选一**：从手牌放一枚新棋，或移动一枚已入场的棋。**自己的蜂后落下
  之前不能移动任何棋子**；前三个回合都没放蜂后，第四个回合唯一的合法着法就是
  放蜂后（:data:`QUEEN_DEADLINE`）。
* **放子限制**：第一枚放世界原点 ``(0, 0)``；对方的第二枚必须贴上去；从第三枚
  起，新棋必须至少接触一枚己方棋、且**不得接触任何敌方棋**。叠层在这里天然正确
  —— 判定看的是栈顶归属（甲虫爬到对方棋上，那一格就算甲虫那一方的颜色）。
* **一体规则（One Hive）**：移动前后蜂巢都要保持连通。拿走会让蜂巢裂开的棋
  一步都不能动。滑动时每一步的落点都必须仍贴着蜂巢。
* **滑动门（Freedom to Move）**：走一格时，若出发格与目标格共有的那两个邻格
  **都比出发格与目标格（取走移动棋之后）更高**，就挤不过去。蚱蜢跳跃不受限，
  甲虫按叠层高度另算（见 :func:`_steps` 的公式）。
* **胜负**：某方蜂后周围 6 个邻格全被占满即该方负。占位棋**不分敌我**（自己贴上去
  也算）。甲虫压在蜂后**头上**不算包围（判据只看蜂后所在格的 6 个邻格）。
  同一手让双方蜂后同时被围满判和。
* **无子可走**：既无处放子又没有可动的棋时必须停一手 —— 见 :class:`PassMove`。
* **三次重复**（含轮到谁）或连续停两手判和；另有 :data:`MAX_PLY` 保底。

扩展虫（侧栏开关，默认关闭）
----------------------------
* **瓢虫**：恰好两跳 —— 先爬到一枚相邻的棋上，再落到第二枚棋的邻边**空地**。
* **蚊子**：模仿任一相邻（只看相邻格**栈顶**）棋种的走法；本身不接触任何非蚊子的
  棋就走不了。爬到棋堆顶上时只按甲虫走（官方规则）。
* **鼠妇**：走一格（同蜂后），或者把一枚相邻的棋搬到自己邻边的空地 —— 搬运过程中
  自己不移动。**简化说明**：官方还有"不能搬运上一回合刚动过的棋、鼠妇自己上一回合
  动过就不能搬运"两条限制，它们需要跨回合历史状态、且会污染局面哈希（置换表
  命中率下降），本项目**未实现**；其余限制（不能搬被压住的棋、不能搬走蜂巢的
  唯一连接点）均已实现。

搜索裁剪
--------
分支因子开局 20~40、中局 80~180，比大力士棋还大，所以 ``max_branch`` 是硬需求。
``include_walls`` / ``include_special`` 一律**忽略** —— 那是步步为营的语义
（minimax 会按 ``ply < wall_depth`` 逐层关掉 include_walls），若当成"裁剪着法"，
深度 ≥2 的节点就几乎没着法了（四子棋与大力士棋都踩过同一口井）。
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Mapping

from boardgames.core.game import Game, SearchOptions
from boardgames.core.move import Move
from boardgames.core.player import PlayerMeta
from boardgames.games.hive.geometry import (
    DIRECTIONS,
    GATES,
    Pos,
    add,
    are_adjacent,
    hex_distance,
    neighbors,
    offset,
)
from boardgames.games.hive.heuristic import evaluate as _evaluate_static
from boardgames.games.hive.heuristic import merged_weights
from boardgames.games.hive.move import MoveMove, PassMove, PillbugMove, PlaceMove
from boardgames.games.hive.pieces import (
    ANT,
    BEETLE,
    GRASSHOPPER,
    LADYBUG,
    MOSQUITO,
    PILLBUG,
    QUEEN,
    SPIDER,
    Piece,
    active_kinds,
)
from boardgames.games.hive.state import MAX_PLY, HiveState, _canonical, pack

#: 到第几个回合还不放蜂后就会被强制（前三个回合都没放 → 第四个回合只能放蜂后）
QUEEN_DEADLINE = 3

#: 走法的偏好序（排序键用）：机动性越强越先看
KIND_PRIOR: dict[str, float] = {
    ANT: 6.0,
    SPIDER: 4.0,
    BEETLE: 3.0,
    GRASSHOPPER: 2.0,
    LADYBUG: 4.5,
    MOSQUITO: 5.0,
    PILLBUG: 5.5,
    QUEEN: 0.0,
}

#: 热循环用的局部别名（``_steps`` 每秒要跑几千次）
_NB = DIRECTIONS
_GATES = GATES

#: rollout 默认策略用的分支上限（比搜索更保守，rollout 每步都要生成着法）
ROLLOUT_BRANCH = 24


class HiveGame(Game[HiveState, Move]):
    """昆虫棋。"""

    key = "hive"
    display_name = "昆虫棋"

    settings_map = {
        "hive_expansion": "expansion",
    }

    tagline = "Hive · 无边界蜂巢"
    summary = (
        "无边界六边形棋盘，双方各 11 枚昆虫；每回合放一枚新棋或移动一枚已入场的棋，"
        "先把对方蜂后六面围满即胜。"
    )
    goal = "把对方蜂后的六面全部占满"
    rules = (
        "无边界六边形棋盘，双方各 11 枚昆虫，从空盘开始（先手第一枚任意放）",
        "每回合二选一：放一枚新虫入场，或移动一枚已经入场的虫",
        "新放的虫必须只贴己方、不得贴敌方（第一枚除外）",
        "蜂后必须在第 4 回合前落下，在那之前不能移动其它虫",
        "蜂巢必须始终保持一体：移动任何一枚都不能把它拆成两半",
        "移动时挤不过两侧格子都比它高的「门」（free-move / 爬行者规则）",
        "基础虫：蜂后走一格、蚁走任意格、蜘蛛恰好走三格、蚱蜢沿直线跳、甲虫可叠在别的虫头上",
        "被压住的虫不能动；压在上面的甲虫可以爬下来",
        "扩展虫（可在侧栏开启）：蚊子模仿相邻虫种走法，鼠妇搬运相邻棋子，瓢虫跨两格落下",
        "把对方蜂后六面围满即胜；包围不分敌我，但甲虫压在蜂后头上不算一面",
    )
    howto = (
        "点底部手牌卡片（或按数字键 1~8）选虫种，再点亮起的落点放新虫",
        "点盘上己方棋子选中，再点亮起的格子移动它",
        "右键 / Esc 取消当前选择；滚轮缩放画布，按住拖动平移，F 键回到蜂巢",
        "鼠标悬停在棋子上会浮出这一格的堆叠与虫种",
        "N 开新局，U 悔棋，R 认输，Esc 回大厅",
    )
    tips = (
        "蜂后别太早落场 —— 落早了容易被围；但也别拖过第 4 回合",
        "鼠妇能把敌虫搬过来堵住蜂后，也能把自己的虫从险地挪开",
    )
    icon = "hive"

    def __init__(self, expansion: bool = False, *, first_player: int = 0) -> None:
        self.expansion = bool(expansion)
        self.first_player = first_player
        self._kinds = active_kinds(self.expansion)

    # ------------------------------------------------------------------ #
    # 基本信息
    # ------------------------------------------------------------------ #

    def player_count(self) -> int:
        return 2

    def player_meta(self) -> list[PlayerMeta]:
        # 颜色用 RGB 字面量而不是 ui.theme.P0/P1 —— 本包不得依赖 pygame 侧模块。
        # 这两个值与 theme.PLAYER_COLORS 一致，改主题时要同步。
        return [
            PlayerMeta(name="玩家 1", color=(240, 185, 90)),   # 琥珀
            PlayerMeta(name="玩家 2", color=(91, 141, 239)),    # 蓝
        ]

    def initial_state(self, first_player: int | None = None) -> HiveState:
        from boardgames.games.hive.state import initial_state as _initial

        return _initial(
            self.expansion,
            self.first_player if first_player is None else first_player,
        )

    # ------------------------------------------------------------------ #
    # 着法生成
    # ------------------------------------------------------------------ #

    def legal_moves(
        self, state: HiveState, options: SearchOptions | None = None
    ) -> list[Move]:
        """当前玩家的全部合法着法。

        **终局返回空表；非终局但无处可走时返回恰好一个** :class:`PassMove`
        —— 空表会让 MCTS 的 rollout 循环一路索取到抛 ``RuntimeError``
        （AI 线程吞掉异常，表现成"AI 突然不下棋"），minimax 也会把它当成
        "局面价值 0"。
        """
        if state.is_terminal():
            return []
        me = state.current
        occ = state.occupancy()
        tops = state.tops()

        moves: list[Move] = list(self._placements(state, me, occ, tops))
        if state.has_queen(me):
            moves.extend(self._movements(state, me, occ, tops))
        if not moves:
            return [PassMove(me)]

        if options is not None:
            cap = options.max_branch if options.max_branch and options.max_branch > 0 else 0
            # **截断隐含排序**：不开 order 又开了 max_branch 时，被裁掉的是生成顺序里
            # 靠后的那批（先放置、后移动），等于把"移动"这一类系统性砍光 ——
            # 而"围死敌后"恰恰常常靠移动完成。MCTS 传的就是 ``order=False``。
            if options.order or 0 < cap < len(moves):
                context = _OrderContext(state)
                moves.sort(key=context.key, reverse=True)
            if cap:
                moves = moves[:cap]
        return moves

    # ---- 放置 ----

    def _placements(
        self, state: HiveState, me: int, occ: dict[Pos, int], tops: dict[Pos, Piece]
    ) -> list[PlaceMove]:
        hand = state.hand(me)
        if state.played[me] >= QUEEN_DEADLINE and not state.has_queen(me):
            # 蜂后期限：这一回合唯一的合法着法就是放蜂后
            kinds: tuple[str, ...] = (QUEEN,) if hand.get(QUEEN, 0) > 0 else ()
        else:
            kinds = tuple(k for k in self._kinds if hand.get(k, 0) > 0)
        if not kinds:
            return []
        targets = self._placement_targets(me, occ, tops)
        return [PlaceMove(me, kind, pos) for pos in targets for kind in kinds]

    @staticmethod
    def _placement_targets(
        me: int, occ: dict[Pos, int], tops: dict[Pos, Piece]
    ) -> tuple[Pos, ...]:
        if not occ:
            # 第一枚放世界原点
            return ((0, 0),)
        if len(occ) == 1:
            # 对方的第一枚：规则要求必须贴上去（此时还没有己方棋，走不了"贴己不贴敌"）
            only = next(iter(occ))
            return tuple(sorted(n for n in neighbors(only) if n not in occ))

        frontier: set[Pos] = set()
        for pos in occ:
            for n in neighbors(pos):
                if n not in occ:
                    frontier.add(n)

        out: list[Pos] = []
        for pos in sorted(frontier):
            friendly = False
            hostile = False
            for n in neighbors(pos):
                piece = tops.get(n)
                if piece is None:
                    continue
                if piece.owner == me:
                    friendly = True
                else:
                    hostile = True
                    break
            if friendly and not hostile:
                out.append(pos)
        return tuple(out)

    # ---- 移动 ----

    def _movements(
        self, state: HiveState, me: int, occ: dict[Pos, int], tops: dict[Pos, Piece]
    ) -> list[Move]:
        out: list[Move] = []
        for pos in sorted(tops):
            piece = tops[pos]
            if piece.owner != me:
                continue
            out.extend(self._moves_of(state, pos, piece.kind, occ, me, tops))
        return out

    def _moves_of(
        self,
        state: HiveState,
        src: Pos,
        kind: str,
        occ_full: dict[Pos, int],
        me: int,
        tops: dict[Pos, Piece],
    ) -> list[Move]:
        height = occ_full[src]
        # 取走这枚棋之后的占位表 —— 滑动门与"落点要贴蜂巢"都必须按它算
        occ = dict(occ_full)
        if height > 1:
            occ[src] = height - 1
        else:
            occ.pop(src, None)
        h_from = height - 1
        # 能不能把这枚棋从蜂巢里拿出来（一体规则）。鼠妇的**搬运**不移动自己，
        # 所以它不靠这一条，由 _pillbug_moves 单独判断搬运目标。
        removable = _can_remove(src, occ_full)

        if kind == MOSQUITO:
            return self._mosquito_moves(src, occ, occ_full, h_from, removable, me, tops)
        if kind == PILLBUG:
            return _pillbug_moves(src, occ, occ_full, me, h_from, removable, tops)
        if not removable:
            return []
        if kind == BEETLE:
            return _simple_moves(src, occ, h_from, me, BEETLE, allow_climb=True)
        if kind == LADYBUG:
            return _ladybug_moves(src, occ, me)
        if kind == GRASSHOPPER:
            return _grasshopper_moves(src, occ, me)
        if kind == SPIDER:
            return _spider_moves(src, occ, me)
        if kind == ANT:
            return _ant_moves(src, occ, me)
        if kind == QUEEN:
            return _simple_moves(src, occ, h_from, me, QUEEN, allow_climb=False)
        return []

    def _mosquito_moves(
        self,
        src: Pos,
        occ: dict[Pos, int],
        occ_full: dict[Pos, int],
        h_from: int,
        removable: bool,
        me: int,
        tops: dict[Pos, Piece],
    ) -> list[Move]:
        """蚊子：模仿相邻格**栈顶**的虫种；自己爬到棋堆上时只按甲虫走。"""
        if not removable:
            return []
        if h_from > 0:
            # 官方：爬到蜂巢顶上的蚊子只能按甲虫移动
            return _simple_moves(src, occ, h_from, me, MOSQUITO, allow_climb=True)

        mimic: set[str] = set()
        for n in neighbors(src):
            piece = tops.get(n)
            if piece is None or piece.kind == MOSQUITO:
                continue
            mimic.add(piece.kind)

        out: list[Move] = []
        for kind in sorted(mimic):
            if kind == BEETLE:
                out.extend(_simple_moves(src, occ, 0, me, MOSQUITO, allow_climb=True))
            elif kind == GRASSHOPPER:
                out.extend(_grasshopper_moves(src, occ, me, kind=MOSQUITO))
            elif kind == SPIDER:
                out.extend(_spider_moves(src, occ, me, kind=MOSQUITO))
            elif kind == ANT:
                out.extend(_ant_moves(src, occ, me, kind=MOSQUITO))
            elif kind == LADYBUG:
                out.extend(_ladybug_moves(src, occ, me, kind=MOSQUITO))
            elif kind == PILLBUG:
                out.extend(_pillbug_moves(src, occ, occ_full, me, 0, True, tops, kind=MOSQUITO))
            elif kind == QUEEN:
                out.extend(_simple_moves(src, occ, 0, me, MOSQUITO, allow_climb=False))
        return _dedup(out)

    # ------------------------------------------------------------------ #
    # 合法性
    # ------------------------------------------------------------------ #

    def is_legal(self, state: HiveState, move: Move) -> bool:
        if state.is_terminal() or move.player != state.current:
            return False
        if isinstance(move, PassMove):
            return not self._has_real_move(state)
        if not isinstance(move, (PlaceMove, MoveMove, PillbugMove)):
            return False
        # 一律重算着法表再比对 —— Move 上带着 compare=False 的动画附带信息，
        # 逐字段手工校验容易漏；着法表本身不大，重算最简单也最不容易错。
        return any(move == candidate for candidate in self.legal_moves(state))

    def _has_real_move(self, state: HiveState) -> bool:
        me = state.current
        occ = state.occupancy()
        tops = state.tops()
        if self._placements(state, me, occ, tops):
            return True
        return bool(state.has_queen(me) and self._movements(state, me, occ, tops))

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #

    def apply(self, state: HiveState, move: Move) -> HiveState:
        if state.is_terminal():
            raise ValueError("对局已结束，不能再走子")
        me = state.current
        if move.player != me:
            raise ValueError(f"着法属于玩家 {move.player}，但当前轮到 {me}")

        mapping = dict(state.stacks)
        placed = isinstance(move, PlaceMove)
        if placed:
            stack = mapping.get(move.dest, ())
            mapping[move.dest] = stack + (Piece(me, move.kind),)
        elif isinstance(move, MoveMove):
            _relocate(mapping, move.src, move.dest)
        elif isinstance(move, PillbugMove):
            _relocate(mapping, move.carried, move.carried_dest)
        elif not isinstance(move, PassMove):
            raise ValueError(f"未知的着法类型: {type(move).__name__}")

        new_stacks = pack(mapping)
        new_current = 1 - me
        new_ply = state.ply + 1
        new_played = (
            state.played[0] + (1 if me == 0 else 0),
            state.played[1] + (1 if me == 1 else 0),
        )
        is_pass = isinstance(move, PassMove)
        new_passes = state.passes + 1 if is_pass else 0

        winner, drawn = _decide(new_stacks)
        new_hash = hash((_canonical(new_stacks), new_current))
        new_seen = state.seen + (new_hash,)
        if not drawn:
            drawn = (
                new_passes >= 2
                or new_seen.count(new_hash) >= 3
                or new_ply >= MAX_PLY
            )

        return HiveState(
            stacks=new_stacks,
            played=new_played,
            current=new_current,
            ply=new_ply,
            seen=new_seen,
            passes=new_passes,
            expansion=state.expansion,
            winner_player=winner,
            drawn=drawn,
        )

    # ------------------------------------------------------------------ #
    # 评估与模拟
    # ------------------------------------------------------------------ #

    def evaluate(
        self, state: HiveState, player: int, weights: Mapping[str, float] | None = None
    ) -> float:
        return _evaluate_static(state, player, weights)

    def rollout_move(
        self,
        state: HiveState,
        rng: random.Random,
        options: SearchOptions | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> Move:
        """MCTS rollout 的默认策略。

        纯随机的昆虫棋 rollout 几乎永远是"双方互相挪子到 400 手上限判和"，
        拿不到任何价值信号。所以这里刻意做成**带噪声的贪心**：

        1. 以较高概率优先**放置**（蜂巢不长大就永远分不出胜负）；
        2. 一半概率只在排序靠前的那一批里挑（近似贪心），另一半全池随机。
           排序由 :class:`_OrderContext` 给出，已经天然偏向"贴近敌后"。
        """
        if options is None:
            options = SearchOptions(max_branch=ROLLOUT_BRANCH, order=True)
        moves = self.legal_moves(state, options)
        if len(moves) <= 1:
            return moves[0]

        tuned = merged_weights(weights)
        placements = [m for m in moves if isinstance(m, PlaceMove)]
        if placements and rng.random() < tuned.get("p_hive_place", 0.55):
            pool: list[Move] = placements
        else:
            pool = [m for m in moves if not isinstance(m, PassMove)] or moves

        if len(pool) > 2 and rng.random() < 0.5:
            pool = pool[: max(1, len(pool) // 3)]
        return rng.choice(pool)


# ---------------------------------------------------------------------- #
# 单步滑动（含滑动门）
# ---------------------------------------------------------------------- #


def _steps(
    src: Pos, occ: dict[Pos, int], h_from: int, *, allow_climb: bool
) -> list[tuple[Pos, int]]:
    """从 ``src`` 走一格的全部候选 ``(目标格, 目标格层数)``。

    ``occ`` 必须是**已把移动棋取走**的占位表（``occ[src]`` 已减 1），
    这样下面两条判断才成立：

    1. "落点必须仍贴着蜂巢"—— 否则棋子会飘到蜂巢外面；
    2. 滑动门的两个门格高度才正确。

    **滑动门公式**（取自 Gen42 规则的官方 FAQ）：设门格 ``C`` / ``D`` 的高度为
    ``hc`` / ``hd``，出发格与目标格（取走移动棋之后）的高度为 ``hs`` / ``ht``，
    则当且仅当 ``min(hc, hd) > max(hs, ht)`` 时挤不过去。

    * 地面棋走地面格：``hs = ht = 0`` → 两门格都被占就挡住。这就是经典的
      Freedom to Move。
    * 地面甲虫爬上 1 层高的棋堆：``max = 1`` → 需要两门格都 ≥2 才挡得住，
      单枚地面棋挡不住甲虫上爬。
    * 1 层高的甲虫爬过两个全是 1 层棋堆的门：``min = 1``，``max = 1`` → 不挡。
    * 1 层高的甲虫想从两个 2 层棋堆中间穿过：``min = 2 > 1`` → 挡住。

    这里是全库最热的循环（一次着法生成要跑上千次），所以几何全部**内联**成
    整数加减 —— 调 :func:`~boardgames.games.hive.geometry.neighbors` 每次都会
    新建一个 6 元组，实测占了整个着法生成 1/3 的时间。
    """
    sq, sr = src
    get = occ.get
    out: list[tuple[Pos, int]] = []
    append = out.append
    for direction in range(6):
        dq, dr = _NB[direction]
        dst = (sq + dq, sr + dr)
        h_to = get(dst, 0)
        if h_to == 0:
            # 落点必须仍贴着（取出移动棋之后的）蜂巢
            qt = dst[0]
            rt = dst[1]
            touching = False
            for ndq, ndr in _NB:
                if (qt + ndq, rt + ndr) in occ:
                    touching = True
                    break
            if not touching:
                continue
        elif not allow_climb:
            continue

        level = h_from if h_from > h_to else h_to
        (g1q, g1r), (g2q, g2r) = _GATES[direction]
        if get((sq + g1q, sr + g1r), 0) > level and get((sq + g2q, sr + g2r), 0) > level:
            continue
        append((dst, h_to))
    return out


def _simple_moves(
    src: Pos, occ: dict[Pos, int], h_from: int, me: int, kind: str, *, allow_climb: bool
) -> list[MoveMove]:
    """蜂后 / 甲虫的"走一格"。"""
    return [
        MoveMove(me, src, dst, kind=kind, path=(dst,), from_height=h_from, to_height=h_to)
        for dst, h_to in _steps(src, occ, h_from, allow_climb=allow_climb)
    ]


def _ant_moves(src: Pos, occ: dict[Pos, int], me: int, kind: str = ANT) -> list[MoveMove]:
    """兵蚁：沿蜂巢外缘滑动任意距离（每小步都要过门、都要贴着蜂巢）。"""
    seen = {src}
    queue: deque[tuple[Pos, list[Pos]]] = deque([(src, [])])
    out: list[MoveMove] = []
    while queue:
        cur, path = queue.popleft()
        for dst, _h_to in _steps(cur, occ, 0, allow_climb=False):
            if dst in seen:
                continue
            seen.add(dst)
            new_path = [*path, dst]
            out.append(
                MoveMove(me, src, dst, kind=kind, path=tuple(new_path),
                         from_height=0, to_height=0)
            )
            queue.append((dst, new_path))
    return out


def _spider_moves(src: Pos, occ: dict[Pos, int], me: int, kind: str = SPIDER) -> list[MoveMove]:
    """蜘蛛：**恰好三格**，途中不能重复经过任何一格，也不能停在中途。"""
    out: list[MoveMove] = []
    found: dict[Pos, tuple[Pos, ...]] = {}

    def walk(cur: Pos, path: list[Pos], visited: set[Pos], depth: int) -> None:
        if depth == 3:
            found.setdefault(cur, tuple(path))
            return
        for dst, _h in _steps(cur, occ, 0, allow_climb=False):
            if dst in visited:
                continue
            visited.add(dst)
            path.append(dst)
            walk(dst, path, visited, depth + 1)
            path.pop()
            visited.discard(dst)

    walk(src, [], {src}, 0)
    for dst, path in found.items():
        out.append(MoveMove(me, src, dst, kind=kind, path=path, from_height=0, to_height=0))
    return out


def _grasshopper_moves(
    src: Pos, occ: dict[Pos, int], me: int, kind: str = GRASSHOPPER
) -> list[MoveMove]:
    """蚱蜢：沿六个方向之一跳过**至少一枚**连续的棋，落在第一个空格。

    官方明确：蚱蜢是"真的跳过去"，**不受滑动门限制**，也不需要落点贴蜂巢
    （落点必然贴着它跨过的那一串棋的最后一枚）。
    """
    out: list[MoveMove] = []
    for direction in range(6):
        delta = DIRECTIONS[direction]
        cursor = add(src, direction)
        jumped = 0
        while cursor in occ:
            jumped += 1
            cursor = offset(cursor, delta)
        if jumped:
            out.append(
                MoveMove(me, src, cursor, kind=kind, path=(cursor,),
                         from_height=0, to_height=0)
            )
    return out


def _ladybug_moves(src: Pos, occ: dict[Pos, int], me: int, kind: str = LADYBUG) -> list[MoveMove]:
    """瓢虫：恰好两跳 —— 先爬到相邻的棋上，再落到第二枚棋的邻边空地。"""
    out: list[MoveMove] = []
    for first in neighbors(src):
        if first not in occ:
            continue
        for second in neighbors(first):
            if second not in occ or second == src:
                continue
            for landing in neighbors(second):
                if landing in occ or landing == src:
                    continue
                out.append(
                    MoveMove(me, src, landing, kind=kind, path=(first, second, landing),
                             from_height=0, to_height=0)
                )
    return _dedup(out)


def _pillbug_moves(
    src: Pos,
    occ: dict[Pos, int],
    occ_full: dict[Pos, int],
    me: int,
    h_from: int,
    removable: bool,
    tops: dict[Pos, Piece],
    kind: str = PILLBUG,
) -> list[Move]:
    """鼠妇：走一格（同蜂后），或把一枚相邻的棋搬到自己邻边的空地。

    搬运时**鼠妇自己不移动** —— 规则原文是"抬起旁边的一枚棋，放到自己旁边的
    空位"，两个动作都以鼠妇为中心。
    """
    out: list[Move] = []
    if removable:
        out.extend(_simple_moves(src, occ, h_from, me, kind, allow_climb=False))

    free = [pos for pos in neighbors(src) if pos not in occ_full]
    if not free:
        return out
    for carried in sorted(neighbors(src)):
        piece = tops.get(carried)
        if piece is None:
            continue
        # 被压住的棋不能搬；搬走会让蜂巢裂开的棋也不能搬（一体规则）
        if occ_full.get(carried, 0) > 1 or not _can_remove(carried, occ_full):
            continue
        for dest in free:
            out.append(
                PillbugMove(
                    me, src, src, carried, dest,
                    carried_kind=piece.kind, carried_owner=piece.owner,
                )
            )
    return out


def _dedup(moves: list[Move]) -> list[Move]:
    """按"这一手改变哪几格"去重（蜘蛛 / 瓢虫 / 蚊子可能殊途同归），保留路径最短的一条。

    键**不能只写 ``dest``**：鼠妇的搬运是 ``dest == src``（自己原地不动），
    八手搬运的 ``dest`` 全是同一格，只按 ``dest`` 去重会把它们合并成一手。
    """
    best: dict[tuple, Move] = {}
    for move in moves:
        key: tuple = (
            (move.dest, move.carried, move.carried_dest)
            if isinstance(move, PillbugMove)
            else (move.dest,)
        )
        current = best.get(key)
        if current is None or len(getattr(move, "path", ())) < len(
            getattr(current, "path", ())
        ):
            best[key] = move
    return [best[key] for key in sorted(best)]


# ---------------------------------------------------------------------- #
# 一体规则
# ---------------------------------------------------------------------- #


def _can_remove(src: Pos, occ: dict[Pos, int]) -> bool:
    """把 ``src`` 上的**最上层那枚棋**拿走之后，蜂巢是否仍然连通。

    别用"每次全盘 BFS"的朴素做法，蜂巢局部很稠密，这里的快速路径能省下
    绝大多数 BFS：

    1. 该格还有别的棋垫着（``occ[src] > 1``）→ 拿走顶层不可能断开（规则豁免）；
    2. 邻居 ≤1 个 → 拿走的是一枚叶子，不可能断开；
    3. 恰好 2 个邻居、且这两个邻居**彼此相邻** → 它们自己就绕得过去；
    4. 只有 3 个及以上邻居才真做 BFS —— 而且目标改成"数 ``src`` 的各邻居是否
       互相可达"，一旦全部找到就立刻返回。实测每次着法生成里真正触发 BFS 的
       棋子通常不超过 3 枚。
    """
    if occ.get(src, 0) > 1:
        return True

    sq, sr = src
    nbrs: list[Pos] = []
    for dq, dr in _NB:
        n = (sq + dq, sr + dr)
        if n in occ:
            nbrs.append(n)
    count = len(nbrs)
    if count <= 1:
        return True
    if count == 2:
        aq, ar = nbrs[0]
        bq, br = nbrs[1]
        dq = aq - bq
        dr = ar - br
        if (abs(dq) + abs(dr) + abs(dq + dr)) // 2 == 1:
            return True

    remaining = set(occ)
    remaining.discard(src)
    if not remaining:
        return True
    need = set(nbrs)
    start = nbrs[0]
    seen = {start}
    stack = [start]
    found = 1
    while stack:
        cur = stack.pop()
        cq, cr = cur
        for dq, dr in _NB:
            n = (cq + dq, cr + dr)
            if n in remaining and n not in seen:
                seen.add(n)
                stack.append(n)
                if n in need:
                    found += 1
                    if found == count:
                        return True
    return False


# ---------------------------------------------------------------------- #
# 胜负
# ---------------------------------------------------------------------- #


def _queen_of(stacks, player: int) -> Pos | None:
    for pos, stack in stacks:
        for piece in stack:
            if piece.owner == player and piece.kind == QUEEN:
                return pos
    return None


def _decide(stacks) -> tuple[int | None, bool]:
    """返回 ``(胜者玩家索引, 是否和棋)``。

    判据只看蜂后**所在格**的 6 个邻格有没有棋 —— 所以甲虫压在蜂后头上
    天然不算包围（它压的是同一格，不影响任何邻格）；占位棋也天然不分敌我。
    """
    occupied = {pos for pos, _ in stacks}
    losers: list[int] = []
    for player in (0, 1):
        queen = _queen_of(stacks, player)
        if queen is None:
            continue
        if all(n in occupied for n in neighbors(queen)):
            losers.append(player)
    if len(losers) == 2:
        # 同一手让双方蜂后同时被围满 → 和棋
        return None, True
    if len(losers) == 1:
        return 1 - losers[0], False
    return None, False


# ---------------------------------------------------------------------- #
# 排序
# ---------------------------------------------------------------------- #


def _relocate(mapping: dict[Pos, tuple[Piece, ...]], src: Pos, dest: Pos) -> None:
    """把 ``src`` 的栈顶那枚棋搬到 ``dest`` 的栈顶。"""
    stack = mapping[src]
    if not stack:
        raise ValueError(f"{src} 上没有棋子")
    moved = stack[-1]
    rest = stack[:-1]
    if rest:
        mapping[src] = rest
    else:
        del mapping[src]
    mapping[dest] = mapping.get(dest, ()) + (moved,)


def _around_queen(state: HiveState, player: int, occ: dict[Pos, int]) -> int:
    queen = state.queen_pos(player)
    if queen is None:
        return 0
    return sum(1 for n in neighbors(queen) if n in occ)


class _OrderContext:
    """着法排序用的**一次性**上下文。

    ``list.sort(key=...)`` 对每个元素只调一次 key，但键函数内部如果每次都去
    重算 ``occupancy()`` / ``queen_pos()``（都是 O(棋数)），180 个着法就是几千次
    字典构造。这里把所有需要的东西**预先算一遍**，键函数退化成纯算术。
    """

    __slots__ = ("around_me", "around_opp", "my_queen", "opp_queen", "played_me", "state")

    def __init__(self, state: HiveState) -> None:
        self.state = state
        occ = state.occupancy()
        me = state.current
        opp = 1 - me
        self.opp_queen = state.queen_pos(opp)
        self.my_queen = state.queen_pos(me)
        self.around_opp = _around_queen(state, opp, occ)
        self.played_me = state.played[me]

    def key(self, move: Move) -> tuple[float, int, int]:
        opp_queen = self.opp_queen
        my_queen = self.my_queen
        score = 0.0

        if isinstance(move, PlaceMove):
            dest = move.dest
            after = self.around_opp
            if opp_queen is not None and are_adjacent(dest, opp_queen):
                after += 1
            if after >= 6:
                score += 1e6  # 一步围死敌后
            score += 45.0 * (after - self.around_opp)
            if my_queen is not None and are_adjacent(dest, my_queen):
                score -= 35.0  # 别往自己蜂后身边贴
            if move.kind == QUEEN and self.played_me >= QUEEN_DEADLINE - 1:
                score += 50.0  # 别被拖到强制回合
            score += KIND_PRIOR.get(move.kind, 0.0)
        elif isinstance(move, (MoveMove, PillbugMove)):
            src = move.src
            # 搬运时鼠妇原地不动（``dest == src``），真正改变局面的是**被搬的棋**
            dest = move.carried_dest if isinstance(move, PillbugMove) else move.dest
            after = self.around_opp
            if opp_queen is not None:
                if are_adjacent(src, opp_queen):
                    after -= 1
                if are_adjacent(dest, opp_queen):
                    after += 1
            if after >= 6:
                score += 1e6
            score += 45.0 * (after - self.around_opp)
            if my_queen is not None and are_adjacent(dest, my_queen):
                score -= 25.0
            if isinstance(move, PillbugMove):
                score += 12.0  # 搬运是稀有战术资源，别被裁掉
            score += KIND_PRIOR.get(getattr(move, "kind", "") or "", 0.0)
        else:
            # 停一手：永远排最后，而且它没有 dest 可算
            return (-1e9, 0, 0)

        if opp_queen is not None:
            score -= 1.5 * hex_distance(dest, opp_queen)
        # 末尾两个坐标保证排序**完全确定**（同分时不能让顺序随哈希随机化变化）。
        # 刻意不用 move.describe()：那是 f-string，排序时每个着法都要拼一次，
        # 实测比整个键的算术还贵。
        return (score, dest[0], dest[1])
