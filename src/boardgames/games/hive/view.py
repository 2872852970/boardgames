"""昆虫棋的棋盘渲染与交互：**无边界画布** + 底部手牌条。

与另外三个棋类最本质的差别
--------------------------
那三家的棋盘是固定的，``layout()`` 里把"缩放 = 可用区域 / 包围盒"一次算完，
之后一辈子不变。昆虫棋不行：

* 蜂巢由已落的棋子长出来，**没有边界**，可以往六个方向一直延伸；
* 开局只有一枚棋，包围盒退化成一个点，固定缩放会飙到几百倍。

所以视角交给 :class:`~boardgames.ui.camera.Camera`（玩家滚轮缩放 / 拖拽平移，
F 键回到蜂巢），本视图只负责把 **axial 格坐标 → 世界像素** 交给它换算。

坐标系（**只有一个地方做世界→屏幕**）
--------------------------------------
::

    axial (q, r) --axial_to_pixel--> 世界像素 --Camera--> 屏幕像素

反向命中测试严格倒着走一遍。任何一处偷偷多算一次缩放 / 平移，就会出现
"看着点在 A 格、实际落在 B 格"，而且只在缩放不为 1 时才发作。

交互：手牌条 + 两段式点击
--------------------------
1. 点底部手牌条上的一张卡 → 选中虫种，盘面上亮出所有可落点；
2. 点一个绿色格子 → 落子；
3. 或者点棋盘上己方一枚棋 → 亮出它的全部落点，再点落点走子；
4. 鼠妇的搬运要**三次**点击：选鼠妇 → 点要搬的那枚棋 → 点落点。
   少一次就会有歧义 —— "把旁边的棋搬到 X" 与 "自己走到 X" 的落点是同一批格子。

素材
----
``assets/<kind>.png``（剪影）与 ``assets/<kind>.line.png``（线稿）是
OpenMoji（CC0）预光栅化的白模，运行时染成玩家色；加载失败时退化成程序绘制的
六边形棋子，绝不因为少一个文件就崩。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

from boardgames.core.move import Move
from boardgames.games.hive.geometry import (
    Pos,
    axial_to_pixel,
    bounding_pixel_box,
    hex_points,
    neighbors,
    pixel_to_axial,
)
from boardgames.games.hive.move import MoveMove, PillbugMove, PlaceMove
from boardgames.games.hive.pieces import (
    KIND_HINTS,
    KIND_LABELS,
    KIND_TINTS,
    active_kinds,
)
from boardgames.games.hive.state import HiveState
from boardgames.ui import render, theme
from boardgames.ui.animation import Tween
from boardgames.ui.board_view import ViewState
from boardgames.ui.camera import Camera
from boardgames.ui.fonts import FontBook

#: **世界坐标**下六边形的外接圆半径。缩放由 Camera 负责，这里恒为 1:1
HEX_SIZE = 38.0
#: 棋子方形贴图的半边长 / 六边形半径
PIECE_RATIO = 0.92
#: 叠层时每往上一层，往上抬多少（占半径的比例）+ 缩小多少
STACK_LIFT = 0.30
STACK_SHRINK = 0.10

# ---------- 棋子配色 ----------
# 一句话原则：**棋盘上的棋子只有玩家色，没有虫种色。**
#
# 中间试过"身体玩家色 + 虫种色镶边"的路子：棋盘是好看了，但一盘子看过去
# 最抢眼的变成了虫种色，敌我反而要靠推理。既然虫种有一张完全不同的剪影
# （八个 OpenMoji 图标互相都认得出），就没必要拿颜色去抢这块地盘 ——
# 虫种交给**剪影 + 悬停浮窗 + 手牌卡片的虫种色底边**（那三处都不在棋盘上，
# 抢不走任何敌我信号）。
#
# 所以下面两个"偏色"常量现在都是 0：留着它们只是为了日后想调回来时有地方改。
#: 身体掺的虫种色比例（恒为 0，见 :func:`body_color`）
KIND_BODY_BLEND = 0.0
#: 线稿掺的虫种色比例（恒为 0，见 :func:`line_color`）
KIND_LINE_BLEND = 0.0
#: 外描边宽度 / 棋子半径 —— 一圈**玩家深色**，让棋子在深色底板上有个轮廓。
#: 纯装饰：既不表达虫种，也不参与命中判定。
RIM_RATIO = 0.09
RIM_MIN = 2

# ---------- 底部手牌条 ----------
HAND_H = 88
#: 手牌条高度的上下限与占比。矮窗口（笔记本横屏 / 被压扁的窗口）里固定 88px
#: 会吃掉画布的一大块，所以跟窗口高度一起缩放，再夹进这个区间。
HAND_H_MIN = 60
HAND_H_MAX = 104
HAND_RATIO = 0.12
HAND_PAD = 12
#: 最左边给「手牌」两个字的专属宽度。
#:
#: **必须留出来**：卡片是后画的（不透明底色），标签和卡片同高的话会被整块盖住 ——
#: 之前就是"标签明明画了却一个字也看不到"。留 30px 只够两个字，所以标签只写「手牌」。
HAND_LABEL_W = 30
#: 窄于这两个宽度就分别把「手牌」标签 / 双方余量胶囊让掉（先保卡片）
LABEL_MIN_WIDTH = 400
CHIP_MIN_WIDTH = 680
CARD_W = 60
CARD_H = 62
CARD_MIN_W = 26
CARD_GAP = 8
#: 右侧「玩家1 N · 玩家2 N」胶囊的宽度
CHIP_W = 148

# ---------- 叠层浮窗 ----------
POPUP_W = 172
POPUP_ROW_H = 26
POPUP_PAD = 8
POPUP_TITLE_H = 20

# ---------- 自动适配 ----------
#: 自动适配的软上限 —— **就是 100%，开局不许放大**。
#:
#: 曾经给到 2.5，理由是"大屏上开局格子大一点好看"，结果开局空盘被放成 201%
#: 贴满画布，玩家看到的是"界面失控了"。100% 时一枚棋直径约 70px，已经足够
#: 点得准、看得清。
#:
#: 那"分辨率自适应"体现在哪？体现在**装不下的时候会缩**：同一局面在
#: 1366×768 上可能只有 60%，在 2560×1440 上就能保持 100%。只会缩、不会放。
AUTO_FIT_MAX_SCALE = 1.0
#: 自动适配留的边距（比通用值紧一点：棋盘才是主角，别留一大圈空白）
AUTO_FIT_PADDING = 0.68

_ASSET_DIR = Path(__file__).parent / "assets"
_MOLDS: dict[str, pygame.Surface | None] = {}
_LINES: dict[str, pygame.Surface | None] = {}
_SPRITES: dict[tuple[str, int, int], pygame.Surface] = {}


# --------------------------------------------------------------------------- #
# 素材
# --------------------------------------------------------------------------- #


def _load(name: str, cache: dict[str, pygame.Surface | None]) -> pygame.Surface | None:
    if name in cache:
        return cache[name]
    image: pygame.Surface | None = None
    try:
        loaded = pygame.image.load(str(_ASSET_DIR / name))
        try:
            image = loaded.convert_alpha()
        except pygame.error:  # pragma: no cover - 极端环境下没有 display
            image = loaded
    except (pygame.error, FileNotFoundError, OSError):
        image = None
    cache[name] = image
    return image


def _mold(kind: str) -> pygame.Surface | None:
    return _load(f"{kind}.png", _MOLDS)


def _line(kind: str) -> pygame.Surface | None:
    return _load(f"{kind}.line.png", _LINES)


def kind_tint(kind: str) -> theme.RGB:
    """虫种专属色调（未与玩家色混合的原始值）。"""
    return KIND_TINTS.get(kind, theme.TEXT)


def body_color(kind: str, player: int) -> theme.RGB:
    """棋子身体的颜色 —— **纯玩家色**。

    :data:`KIND_BODY_BLEND` 是 0。曾经给到 0.30，结果一棋盘读全是虫种色，
    "玩家 1 的甲虫"和"玩家 2 的鼠妇"撞脸。参数留着是为了日后想再试时有地方改。
    """
    return theme.mix(theme.PLAYER_COLORS[player], kind_tint(kind), KIND_BODY_BLEND)


def line_color(kind: str, player: int) -> theme.RGB:
    """线稿（轮廓 / 斑点 / 体节）的颜色 —— **纯玩家深色**（同 :data:`KIND_LINE_BLEND`）。"""
    return theme.mix(theme.PLAYER_DARK[player], kind_tint(kind), KIND_LINE_BLEND)


def hand_height(area_height: int) -> int:
    """手牌条该占多高 —— 跟着窗口高度走，夹在 :data:`HAND_H_MIN` ~ :data:`HAND_H_MAX`。

    固定高度在矮窗口里会把画布挤扁（棋盘才是主角），在高分屏上又显得小气。
    """
    return max(HAND_H_MIN, min(HAND_H_MAX, int(area_height * HAND_RATIO)))


def _plate(kind: str, radius: int, grow: int, color: theme.RGB) -> pygame.Surface:
    """把剪影整体放大 ``grow`` 像素再填成纯色 —— 也就是一圈跟着轮廓走的描边。

    素材缺失时退化成"大一圈的六边形"，效果一样（还是那圈颜色）。
    """
    side = (radius + grow) * 2
    plate = pygame.Surface((side, side), pygame.SRCALPHA)
    mold = _mold(kind)
    if mold is None:
        mid = side / 2.0
        points = [(mid + x, mid + y) for x, y in hex_points((0.0, 0.0), radius + grow)]
        pygame.draw.polygon(plate, (*color, 255), points)
        return plate
    plate.blit(pygame.transform.smoothscale(mold, (side, side)), (0, 0))
    plate.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return plate


def _procedural(kind: str, player: int, size: int) -> pygame.Surface:
    """素材缺失时的兜底棋子：一枚带深色描边的六边形 + 蜂后加一圈王冠点。

    颜色仍然按"身体 = 玩家色、描边 = 玩家深色掺虫种色"来，免得兜底棋子看着
    像另一套东西。
    """
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    mid = size / 2.0
    points = [(mid + x, mid + y) for x, y in hex_points((0.0, 0.0), mid * 0.92)]
    pygame.draw.polygon(layer, (*line_color(kind, player), 255), points)
    pygame.draw.polygon(
        layer,
        (*body_color(kind, player), 255),
        [(mid + (x - mid) * 0.82, mid + (y - mid) * 0.82) for x, y in points],
    )
    if kind == "queen":
        for i in (-1, 0, 1):
            pygame.draw.circle(
                layer, theme.TEXT, (int(mid + i * mid * 0.42), int(mid - mid * 0.42)),
                max(1, size // 22),
            )
    return layer


def sprite(kind: str, player: int, radius: int) -> pygame.Surface:
    """一枚染色后的棋子贴图（带缓存 —— 每帧现染 + 现缩放会明显掉帧）。

    自下而上三层，表达的全是**敌我**，一点虫种色都不掺：

    1. **外描边**：剪影放大 :data:`RIM_RATIO` 后填玩家**深**色 —— 给个轮廓；
    2. **身体**：剪影填纯玩家色 —— 面积最大的一层，"这是谁的棋"就靠它；
    3. **线稿**：轮廓 / 斑点 / 体节，填玩家深色。

    虫种靠剪影（八个图标互相都认得出）+ 悬停浮窗 + 手牌卡片的虫种色底边。

    返回的贴图**以中心为准**，比 ``2*radius`` 每边大 ``rim`` 像素；
    调用方一律按中心摆放（描边不能算进命中几何，否则点击范围会跟着变色）。
    """
    radius = max(4, int(radius))
    key = (kind, player, radius)
    cached = _SPRITES.get(key)
    if cached is not None:
        return cached

    rim = max(RIM_MIN, int(radius * RIM_RATIO))
    size = radius * 2
    image = _plate(kind, radius, rim, theme.PLAYER_DARK[player])

    mold = _mold(kind)
    if mold is None:
        body = _procedural(kind, player, size)
    else:
        body = pygame.Surface((size, size), pygame.SRCALPHA)
        body.blit(pygame.transform.smoothscale(mold, (size, size)), (0, 0))
        body.fill((*body_color(kind, player), 255), special_flags=pygame.BLEND_RGBA_MULT)
        strokes = _line(kind)
        if strokes is not None:
            overlay = pygame.transform.smoothscale(strokes, (size, size))
            overlay.fill((*line_color(kind, player), 255), special_flags=pygame.BLEND_RGBA_MULT)
            body.blit(overlay, (0, 0))
    image.blit(body, (rim, rim))

    if len(_SPRITES) > 240:  # 缩放档位太多时整体丢弃，避免无上限增长
        _SPRITES.clear()
    _SPRITES[key] = image
    return image


# --------------------------------------------------------------------------- #
# 动画
# --------------------------------------------------------------------------- #


@dataclass
class _Anim:
    """一步着法的入场动画。"""

    move: Move
    tween: Tween
    #: 途经的**世界**格子（首元素是出发格，末元素是落点）
    path: tuple[Pos, ...]
    #: 被搬动的那一枚（鼠妇搬运时鼠妇自己不动）
    hidden: Pos
    kind: str
    owner: int
    #: 出发格所在的层号（甲虫下堆时要从高处滑下来）
    from_height: int = 0
    to_height: int = 0


class HiveView:
    """昆虫棋的棋盘视图。"""

    def __init__(self) -> None:
        self.area = pygame.Rect(0, 0, 600, 600)
        #: 画布视口（``area`` 去掉底部手牌条）—— 也是摄像机的视口
        self.canvas = pygame.Rect(0, 0, 600, 600 - HAND_H)
        #: 手牌条
        self.hand_rect = pygame.Rect(0, 600 - HAND_H, 600, HAND_H)
        #: 手牌条当前实际高度（随窗口高度变，见 :func:`hand_height`）
        self.hand_h = HAND_H
        self.camera = Camera()

        self._anim: _Anim | None = None
        self._last_move: Move | None = None
        #: 手牌条里选中的虫种
        self._picked: str | None = None
        #: 棋盘上选中的格子
        self._selected: Pos | None = None
        #: 鼠妇搬运：已被点中的"要搬走的那一枚"
        self._carry: Pos | None = None
        #: 落点 -> 着法（点这一格就走这一手）
        self._moves: dict[Pos, Move] = {}
        #: 可以被鼠妇搬走的那一批棋（点它进入搬运落点选择）
        self._carryable: frozenset[Pos] = frozenset()
        self._hover: Pos | None = None
        self._hover_card: str | None = None
        self._cards: dict[str, pygame.Rect] = {}
        #: 手牌条左侧的「手牌」标签与右侧双方余量胶囊这次画不画
        self._show_hand_label = True
        self._show_hand_chip = True
        self._state: HiveState | None = None
        #: 落点表是否已与当前选择同步（避免每帧都重算一遍着法）
        self._refreshed = False

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #

    def layout(self, area: pygame.Rect) -> None:
        """切分画布与手牌条。

        手牌条高度**跟着窗口高度走**（:func:`hand_height`）：固定 88px 在
        1366×768 这类矮窗口里会吃掉画布的六分之一，棋盘被挤扁；
        而 4K 竖屏上又显得小气。
        """
        self.area = pygame.Rect(area)
        hand_h = hand_height(area.height)
        height = max(HAND_H_MIN + 60, area.height - hand_h)
        self.canvas = pygame.Rect(area.x, area.y, area.width, height)
        self.hand_rect = pygame.Rect(
            area.x, area.y + height, area.width, max(0, area.height - height)
        )
        self.hand_h = self.hand_rect.height

    def camera_viewport(self) -> pygame.Rect:
        """摄像机的视口 = 画布（**不含**手牌条）。

        手牌条里的点击不该被当成"拖拽画布"，所以必须把它排除在视口外。
        """
        return self.canvas

    def auto_fit_camera(self, state: HiveState | None = None) -> None:
        """把蜂巢塞进画布。

        ``padding`` 给 0.68 而不是接近 1：蜂巢贴着画布边缘会显得很挤。

        ``max_scale`` 见 :data:`AUTO_FIT_MAX_SCALE`（= 1.0，**只缩不放**）：
        开局那七格内容太少，"装下"会算出 400% 这种荒唐值，必须有个上限。
        什么时候该缩由内容包围盒与视口尺寸的比决定，所以分辨率自适应照旧。

        调用时机由场景掌勺（见 ``MatchScene._auto_fit_camera``）——
        不是每帧调用，而是"内容跑出视口"时才调用。
        """
        state = state if state is not None else self._state
        if state is None:
            return
        self.camera.fit(
            self.world_bounds(state),
            padding=AUTO_FIT_PADDING,
            max_scale=AUTO_FIT_MAX_SCALE,
        )

    def hud_inset(self) -> int:
        """底部操作提示要往上让开手牌条（外加一点呼吸空间）。"""
        return self.hand_h + 26

    def idle_hint(self) -> str:
        return "选手牌放子 或 点己方棋子走子"

    # ------------------------------------------------------------------ #
    # 坐标换算（全模块唯一一处）
    # ------------------------------------------------------------------ #

    def hex_px(self) -> float:
        """当前缩放下，一个六边形外接圆半径的屏幕像素数。"""
        return HEX_SIZE * self.camera.scale

    def world_of(self, pos: Pos) -> tuple[float, float]:
        """axial -> **世界**像素。"""
        return axial_to_pixel(pos, HEX_SIZE)

    def cell_center(self, pos: Pos, height: int = 0) -> tuple[float, float]:
        """axial -> **屏幕**像素中心。

        ``height`` 是该枚棋在栈里的层号（0 = 地面）—— 叠层要往上抬一点并且
        略微缩小，否则甲虫压在别人头上完全看不出来。
        """
        wx, wy = self.world_of(pos)
        sx, sy = self.camera.world_to_screen(wx, wy)
        radius = self.hex_px()
        lift = radius * STACK_LIFT * height
        return (sx, sy - lift)

    def pos_at(self, screen: tuple[int, int]) -> Pos | None:
        """屏幕像素 -> axial；画布外返回 ``None``。"""
        if not self.canvas.collidepoint(screen):
            return None
        wx, wy = self.camera.screen_to_world(screen[0], screen[1])
        return pixel_to_axial(wx, wy, HEX_SIZE)

    def piece_radius(self, height: int = 0) -> int:
        radius = self.hex_px() * PIECE_RATIO * (1.0 - STACK_SHRINK * height)
        return max(4, int(radius))

    def world_bounds(self, state: HiveState) -> pygame.Rect:
        """蜂巢的世界包围盒（给摄像机自动适配用）。

        空盘时返回原点周围一圈 —— 否则第一枚棋会被"适配"到几百倍缩放。
        """
        points = list(state.occupied())
        if not points:
            points = [(0, 0), *neighbors((0, 0))]
        left, top, right, bottom = bounding_pixel_box(points, HEX_SIZE)
        return pygame.Rect(
            int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top))
        )

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #

    def _sync_state(self, state: HiveState) -> None:
        """局面对象换了就清空选择（落子 / 悔棋 / 新局都会换对象）。"""
        if self._state is not state:
            self._state = state
            self._picked = None
            self._selected = None
            self._carry = None
            self._moves = {}
            self._carryable = frozenset()
            self._refreshed = False

    def _clear(self) -> None:
        self._picked = None
        self._selected = None
        self._carry = None
        self._moves = {}
        self._carryable = frozenset()
        self._refreshed = True

    # ---- 给 MatchScene 的可选钩子（Esc / 右键 / 数字键）----

    def has_selection(self) -> bool:
        """眼下是否"举着"东西（手牌虫种 / 盘上棋子 / 鼠妇要搬的那枚）。

        ``MatchScene`` 用 ``hasattr`` 探测：有它的话 Esc 与右键会先用来
        "取消选择"，而不是一路直接把玩家踢回大厅。
        """
        return self._picked is not None or self._selected is not None

    def clear_selection(self) -> None:
        """取消当前选择（右键 / Esc）。"""
        self._clear()

    def active_hand_kinds(self, state: HiveState) -> tuple[str, ...]:
        """手牌条上的虫种顺序 —— 数字键就是照这个顺序编号的。"""
        return active_kinds(state.expansion)

    def pick_kind(self, kind: str, game, state: HiveState, view: ViewState) -> str | None:
        """按虫种直接选手牌（数字键 1..8，等价于点那张卡）。

        返回选中虫种的中文名；选不中（没这种虫 / 已经用光 / 局面结束）返回
        ``None`` —— 文案由视图给，``MatchScene`` 不需要认识任何虫种。
        """
        if not isinstance(state, HiveState) or state.is_terminal():
            return None
        self._sync_state(state)
        player = state.current
        if kind not in active_kinds(state.expansion) or state.hand_left(player, kind) <= 0:
            return None
        # 再按一次同一个键 = 取消（和再点一次卡片一致）
        if self._picked == kind:
            self._clear()
            return None
        self._choose_kind(kind, game, state)
        return KIND_LABELS.get(kind, kind)

    def _choose_kind(self, kind: str, game, state: HiveState) -> None:
        player = state.current
        self._picked = kind
        self._selected = None
        self._carry = None
        self._refresh(game, state, player)

    def _refresh(self, game, state: HiveState, player: int) -> None:
        """按当前选择重算落点表。"""
        self._refreshed = True
        self._moves = {}
        self._carryable = frozenset()
        if not state.has_queen(player) and self._selected is not None:
            self._selected = None  # 蜂后没落场就一枚棋都动不了

        moves = game.legal_moves(state)
        if self._picked is not None:
            for move in moves:
                if isinstance(move, PlaceMove) and move.kind == self._picked:
                    self._moves.setdefault(move.dest, move)
            return
        if self._selected is None:
            return

        carry: set[Pos] = set()
        for move in moves:
            if isinstance(move, PillbugMove) and move.src == self._selected:
                if self._carry is None:
                    carry.add(move.carried)
                elif move.carried == self._carry:
                    self._moves.setdefault(move.carried_dest, move)
            elif (
                isinstance(move, MoveMove)
                and move.src == self._selected
                and self._carry is None
            ):
                self._moves.setdefault(move.dest, move)
        self._carryable = frozenset(carry)

    def handle_motion(self, pos, game, state: HiveState, view: ViewState) -> None:
        view.mouse = pos
        if not isinstance(state, HiveState):
            self._hover = None
            return
        self._sync_state(state)
        self._hover_card = self._card_at(pos)
        self._hover = None if self._hover_card else self.pos_at(pos)

    def handle_click(self, pos, game, state: HiveState, view: ViewState) -> Move | None:
        if not isinstance(state, HiveState) or state.is_terminal():
            return None
        self._sync_state(state)
        # 人机对战里 AI 回合不该有任何可点的东西 —— 场景那边已经用
        # `interactive=False` 挡了一道，这里再自洽一道（视图不依赖调用方）。
        pov = getattr(view, "pov_player", None)
        if pov is not None and pov != state.current:
            return None
        player = state.current

        # 1) 手牌条
        kind = self._card_at(pos)
        if kind is not None and state.hand_left(player, kind) > 0:
            if self._picked == kind:
                self._clear()  # 再点一次同一张卡 = 取消
            else:
                self._choose_kind(kind, game, state)
            return None

        cell = self.pos_at(pos)
        if cell is None:
            # 点到手牌条的空白处 / 棋盘外的留白 —— 一样算"取消选择"，
            # 否则玩家会发现"点了空白处反而还举着一枚棋"
            if kind is None:
                self._clear()
            return None

        # 2) 点在落点上 -> 出招
        move = self._moves.get(cell)
        if move is not None:
            self._clear()
            return move

        # 3) 点"可被鼠妇搬走"的那枚棋 -> 进入搬运落点选择
        if cell in self._carryable:
            self._carry = cell
            self._refresh(game, state, player)
            return None

        # 4) 点己方棋子 -> 选中它
        if state.owner_at(cell) == player:
            self._selected = cell
            self._picked = None
            self._carry = None
            self._refresh(game, state, player)
            return None

        # 5) 点别处 -> 取消选择
        self._clear()
        return None

    def hover_hint(self, view: ViewState) -> tuple[str, tuple[int, int, int]]:
        state = self._state
        if state is None:
            return "", theme.TEXT_FAINT
        if self._hover_card is not None:
            label = KIND_LABELS.get(self._hover_card, self._hover_card)
            return f"{label}：{KIND_HINTS.get(self._hover_card, '')}", theme.ACCENT
        if self._hover is None:
            return "", theme.TEXT_FAINT
        move = self._moves.get(self._hover)
        if move is not None:
            return move.describe(), theme.OK
        if self._hover in self._carryable:
            return "点这枚棋，让鼠妇把它搬走", theme.ACCENT
        piece = state.top(self._hover)
        if piece is not None:
            stack = state.stack_at(self._hover)
            if len(stack) > 1:
                # 详细的每一层交给浮窗（见 hover_popup），这里只给一句摘要
                below = "、".join(item.label for item in reversed(stack[:-1]))
                return f"{piece.label} 压着 {below}", theme.WARN
            return f"{piece.label}：{KIND_HINTS.get(piece.kind, '')}", theme.TEXT_DIM
        return "空地", theme.TEXT_FAINT

    def hud_hint(self, *, wall_mode: bool = False, paused: bool = False) -> str:
        if paused:
            return "AI 自对弈已暂停：点棋盘或「单步」推进一步，空格继续自动对弈"
        return (
            "点手牌或己方棋子 · 数字键 1-8 选虫种 · 右键 / Esc 取消 · "
            "滚轮缩放 · 拖动平移 · F 回到蜂巢"
        )

    def hover_popup(self, state) -> tuple[pygame.Rect, tuple[tuple[int, str, bool], ...]] | None:
        """鼠标悬停在一枚（或一摞）棋上时，浮窗的矩形与内容（``None`` = 不该画）。

        内容每项是 ``(owner, kind, is_top)``，**自上而下**排列（顶在最前）。

        两个都要靠它：

        * **叠层**：画面上只看得到最上面那一枚，而"甲虫压在蜂后头上"与
          "蜂后压着甲虫"胜负正好相反 —— 光看画面玩家不知道底下是谁；
        * **单层**：棋子本身只有玩家色（敌我识别优先，见 :func:`sprite`），
          虫种就靠这张浮窗来报 —— 悬停一下就知道"这是玩家 2 的蚊子"，
          比给八种虫各配一种颜色省事，也不跟敌我信号抢注意力。
        """
        pos = self._hover
        if pos is None or state is None:
            return None
        stack = state.stack_at(pos)
        if not stack:
            return None
        # ``stack_at`` 是**自下而上**，翻过来之后**下标 0 才是顶上那一枚** ——
        # 写成 ``len(stack) - 1`` 会把高亮打到最底下那一行上。
        rows = tuple(
            (piece.owner, piece.kind, index == 0)
            for index, piece in enumerate(reversed(stack))
        )
        # 只有一枚棋时不写标题 —— 标题里的"虫种 · 玩家"和那一行本身是同一件事，
        # 紧凑一条反而更像"贴在棋子旁边的标签"。
        title_h = POPUP_TITLE_H if len(rows) > 1 else 0
        height = POPUP_PAD * 2 + title_h + POPUP_ROW_H * len(rows)
        cx, cy = self.cell_center(pos, len(stack) - 1)
        gap = self.piece_radius() + 12
        left = int(cx + gap)
        if left + POPUP_W > self.canvas.right - 8:
            left = int(cx - gap - POPUP_W)  # 右边塞不下就翻到左边
        left = max(self.canvas.left + 8, min(self.canvas.right - POPUP_W - 8, left))
        top = max(
            self.canvas.top + 8,
            min(self.canvas.bottom - height - 8, int(cy - height / 2)),
        )
        return pygame.Rect(left, top, POPUP_W, height), rows

    def in_placement_mode(self) -> bool:
        """昆虫棋没有"放墙模式"。

        **必须实现**：``MatchScene._place_mode_supported()`` 用 ``hasattr`` 探测，
        缺了它会被当成"支持放墙模式"，右键进模式后按 V 键会崩。
        """
        return False

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #

    def animate(self, move: Move, duration_ms: int) -> None:
        if duration_ms <= 0:
            return
        state = self._state
        if state is None:
            return
        player = move.player
        if isinstance(move, PlaceMove):
            self._anim = _Anim(
                move, Tween(duration_ms / 1000.0), (move.dest,), move.dest,
                move.kind, player,
            )
        elif isinstance(move, PillbugMove):
            self._anim = _Anim(
                move, Tween(duration_ms / 1000.0), (move.carried, move.carried_dest),
                move.carried_dest, move.carried_kind or "", move.carried_owner,
            )
        elif isinstance(move, MoveMove):
            path = (move.src, *move.path) if move.path else (move.src, move.dest)
            self._anim = _Anim(
                move, Tween(duration_ms / 1000.0), path, move.dest,
                move.kind or "", player,
                from_height=move.from_height, to_height=move.to_height,
            )
        else:
            self._anim = None  # 停一手：没有可播的画面

    def update(self, dt_ms: float) -> bool:
        if self._anim is None:
            return False
        if self._anim.tween.update(dt_ms / 1000.0):
            self._anim = None
            return False
        return True

    def is_animating(self) -> bool:
        return self._anim is not None

    def reset(self) -> None:
        self._anim = None
        self._last_move = None
        self._picked = None
        self._selected = None
        self._carry = None
        self._moves = {}
        self._carryable = frozenset()
        self._hover = None
        self._hover_card = None

    def set_last_move(self, move: Move | None) -> None:
        self._last_move = move

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #

    def draw(
        self,
        surface: pygame.Surface,
        fonts: FontBook,
        game,
        state: HiveState,
        view: ViewState,
        *,
        interactive: bool,
    ) -> None:
        self._sync_state(state)
        self._drop_foreign_selection(view, state)
        self._draw_canvas_bg(surface)

        # 人机对战时手牌条与提示都钉在**我方**（见 _hand_player）：
        # 轮到 AI 时不能把对手的手牌、可选棋子、落点提示摊开给玩家看。
        mine = self._hand_player(view) == state.current
        clip = surface.get_clip()
        surface.set_clip(self.canvas)
        try:
            self._draw_cells(surface, state)
            if interactive and mine:
                self._refresh_if_stale(game, state)
                self._draw_selection(surface)
            self._draw_pieces(surface, fonts, state)
            if interactive and mine:
                # 落点提示画在棋子**之上**：棋子贴图比方格大，先画的话
                # 紧贴邻格的落点会被旁边那枚棋盖掉半边，看着像"这手不能走"。
                self._draw_hints(surface, state)
            self._draw_hover_popup(surface, fonts, state)
        finally:
            surface.set_clip(clip)

        self._draw_hand(surface, fonts, state, interactive and mine, view)
        self._draw_scale_chip(surface, fonts)

    def _hand_player(self, view: ViewState) -> int:
        """手牌条该画谁的手牌。

        * 双人同屏 / AI 自对弈：``view.pov_player is None`` → 跟随当前行动方
          （谁走棋就显示谁的手牌，轮流交接时看得到对方还剩什么）。
        * 人机对战：钉在**人类那一方**（``view.pov_player``）。不钉的话轮到 AI 时
          整个手牌条会切到对手那边，玩家等于免费看到对手的手牌与可落点。
        """
        pov = getattr(view, "pov_player", None)
        if pov is None:
            return self._state.current if self._state is not None else 0
        return pov

    def _drop_foreign_selection(self, view: ViewState, state: HiveState) -> None:
        """视角方不是当前行动方时，清掉残留的选择与落点表。

        否则人类上一手留下的"举着的棋子 + 落点"会在对手回合一帧帧重新亮起来 ——
        看起来就像在预览对手能走哪。
        """
        if getattr(view, "pov_player", None) is None:
            return
        if view.pov_player == state.current:
            return
        if self._picked is None and self._selected is None and self._carry is None and not self._moves:
            return
        self._picked = None
        self._selected = None
        self._carry = None
        self._moves = {}
        self._carryable = frozenset()
        self._refreshed = True  # 别让 _refresh_if_stale 又按 state.current 算一遍

    def _refresh_if_stale(self, game, state: HiveState) -> None:
        """选择刚变过、落点表还没跟上时补算一次。

        用 ``_refreshed`` 标记而不是"看表是不是空的"：选中一枚**无处可走**的棋
        （表就是空的）时，后者会每帧都重算一遍着法生成。
        """
        if self._refreshed or (self._picked is None and self._selected is None):
            return
        self._refresh(game, state, state.current)

    def _draw_canvas_bg(self, surface: pygame.Surface) -> None:
        render.panel(
            surface, self.canvas.inflate(-2, -2), color=theme.BOARD_BG,
            radius=theme.RADIUS + 6, shadow=False,
        )

    def _draw_cells(self, surface: pygame.Surface, state: HiveState) -> None:
        """只画"有棋的格子 + 它们的外圈" —— 无限棋盘不可能全画。

        空盘时**额外画一枚原点格**：规则要求第一枚落在世界原点，不画个标记
        玩家对着空画布完全不知道该往哪点。
        """
        occupied = set(state.occupied())
        if not occupied:
            pygame.draw.polygon(surface, theme.CELL, self._hex((0, 0), 0.98))
            pygame.draw.polygon(surface, theme.BORDER, self._hex((0, 0), 0.98), 1)
            return
        frontier: set[Pos] = set()
        for pos in occupied:
            for n in neighbors(pos):
                if n not in occupied:
                    frontier.add(n)

        radius = self.hex_px()
        visible = self.camera.visible_world_rect().inflate(
            int(radius * 2), int(radius * 2)
        )
        for pos in frontier:
            if not self._visible(pos, visible):
                continue
            points = self._hex(pos, 0.98)
            pygame.draw.polygon(surface, theme.BORDER_SOFT, points, 1)
        for pos in occupied:
            if not self._visible(pos, visible):
                continue
            pygame.draw.polygon(surface, theme.CELL, self._hex(pos, 0.98))
            pygame.draw.polygon(surface, theme.CELL_ALT, self._hex(pos, 0.98), 1)

    def _visible(self, pos: Pos, visible: pygame.Rect) -> bool:
        wx, wy = self.world_of(pos)
        return visible.collidepoint(int(wx), int(wy))

    def _hex(self, pos: Pos, scale: float = 1.0) -> list[tuple[int, int]]:
        cx, cy = self.cell_center(pos)
        return [
            (int(cx + x), int(cy + y))
            for x, y in hex_points((0.0, 0.0), self.hex_px() * scale)
        ]

    def _draw_hints(self, surface: pygame.Surface, state: HiveState) -> None:
        """落点提示：绿色圆盘（鼠妇搬运用琥珀色区分）。

        画在**棋子之后**（见 :meth:`draw`），并且先描一圈深色再把亮色环压上去 ——
        这样无论底下是空地还是别的棋子的半张翅膀，这一圈都看得见。
        """
        for dest, move in self._moves.items():
            color = theme.WARN if isinstance(move, PillbugMove) else theme.OK
            cx, cy = self.cell_center(dest)
            radius = max(5, int(self.hex_px() * 0.44))
            layer = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
            mid = radius + 4
            pygame.draw.circle(layer, (*theme.SHADOW, 150), (mid, mid), radius + 2)
            pygame.draw.circle(layer, (*color, 70), (mid, mid), radius)
            pygame.draw.circle(layer, (*color, 235), (mid, mid), radius, 2)
            surface.blit(layer, (int(cx) - mid, int(cy) - mid))

        for pos in self._carryable:
            level = max(0, state.height(pos) - 1)
            cx, cy = self.cell_center(pos, level)
            radius = self.piece_radius(level) + 5
            pygame.draw.circle(surface, theme.SHADOW, (int(cx), int(cy)), radius + 1, 4)
            pygame.draw.circle(surface, theme.WARN, (int(cx), int(cy)), radius, 2)

    def _draw_hover_popup(self, surface: pygame.Surface, fonts: FontBook, state: HiveState) -> None:
        """悬停标识：把鼠标下这一枚（或这一摞）摊开列出来。

        每一行 = 迷你棋子 + 虫种名 + 归属（玩家色）；叠层时自上而下就是
        "谁压着谁"，单层时这一行就是**虫种标识**。
        """
        popup = self.hover_popup(state)
        if popup is None:
            return
        rect, rows = popup
        render.panel(surface, rect, color=theme.PANEL, radius=theme.RADIUS_SM)
        radius = (POPUP_ROW_H - 8) // 2
        y = rect.y + POPUP_PAD
        if len(rows) > 1:
            render.text(
                surface, fonts.get(11), f"这一格叠了 {len(rows)} 枚（从上到下）",
                (rect.x + POPUP_PAD, y), theme.TEXT_DIM,
            )
            y += POPUP_TITLE_H
        for owner, kind, is_top in rows:
            row = pygame.Rect(rect.x + 4, y, rect.width - 8, POPUP_ROW_H - 2)
            if len(rows) == 1 or is_top:
                # 单层就这一行；多层只点亮顶上那一枚（"压着别人的是它"）
                render.rounded_rect(surface, row, theme.PANEL_HOVER, theme.RADIUS_SM)
            image = sprite(kind, owner, radius)
            surface.blit(
                image, image.get_rect(center=(row.x + POPUP_PAD + radius, row.centery))
            )
            render.text(
                surface, fonts.get(13), KIND_LABELS.get(kind, kind),
                (row.x + POPUP_PAD + radius * 2 + 6, row.centery),
                theme.TEXT if is_top else theme.TEXT_DIM, baseline="middle",
            )
            render.text(
                surface, fonts.get(11), f"玩家{owner + 1}",
                (row.right - 4, row.centery), theme.PLAYER_COLORS[owner],
                align="right", baseline="middle",
            )
            y += POPUP_ROW_H

    def _draw_selection(self, surface: pygame.Surface) -> None:
        state = self._state
        if state is None or self._selected is None:
            return
        height = max(0, state.height(self._selected) - 1)
        cx, cy = self.cell_center(self._selected, height)
        radius = self.piece_radius(height) + 4
        pygame.draw.circle(surface, theme.SELECT_RING, (int(cx), int(cy)), radius, 2)

    def _draw_pieces(
        self, surface: pygame.Surface, fonts: FontBook, state: HiveState
    ) -> None:
        anim = self._anim
        hidden = anim.hidden if anim is not None else None
        last_cells: frozenset[Pos] = frozenset()
        if isinstance(self._last_move, (PlaceMove, MoveMove, PillbugMove)):
            last_cells = frozenset(self._last_move.destinations())

        visible = self.camera.visible_world_rect().inflate(
            int(self.hex_px() * 3), int(self.hex_px() * 3)
        )
        for pos in state.occupied():
            if not self._visible(pos, visible):
                continue
            stack = state.stack_at(pos)
            for level, piece in enumerate(stack):
                if pos == hidden and level == len(stack) - 1:
                    continue  # 正在飞行中的那一枚，下面单独画
                self._draw_piece(
                    surface, fonts, piece.kind, piece.owner,
                    self.cell_center(pos, level), self.piece_radius(level),
                    active=pos in last_cells and level == len(stack) - 1,
                )
            if len(stack) > 1:
                self._draw_stack_badge(surface, fonts, pos, len(stack))

        if anim is not None:
            progress = anim.tween.eased()  # Tween.eased() 已经包了一层 ease_out_cubic
            cx, cy = self._anim_center(anim, progress)
            radius = self.piece_radius(anim.to_height)
            self._draw_piece(surface, fonts, anim.kind, anim.owner, (cx, cy), radius,
                             active=True)

    def _anim_center(self, anim: _Anim, progress: float) -> tuple[float, float]:
        """沿路径插值（世界坐标插值，再统一换屏幕 —— 只换算一次）。"""
        path = anim.path
        if len(path) == 1:
            wx, wy = self.world_of(path[0])
            return self.camera.world_to_screen(wx, wy)
        segments = len(path) - 1
        scaled = progress * segments
        index = min(segments - 1, int(scaled))
        local = scaled - index
        ax, ay = self.world_of(path[index])
        bx, by = self.world_of(path[index + 1])
        wx = ax + (bx - ax) * local
        wy = ay + (by - ay) * local
        # 爬升 / 下降：在**世界**坐标里插值层高，避免缩放变化时抖动
        lift = HEX_SIZE * STACK_LIFT
        wy -= lift * (anim.from_height + (anim.to_height - anim.from_height) * progress)
        return self.camera.world_to_screen(wx, wy)

    def _draw_piece(
        self,
        surface: pygame.Surface,
        fonts: FontBook,
        kind: str,
        owner: int,
        center: tuple[float, float],
        radius: int,
        *,
        active: bool = False,
    ) -> None:
        image = sprite(kind or "ant", owner, radius)
        cx, cy = int(center[0]), int(center[1])
        if active:
            render.circle_glow(
                surface, (cx, cy), radius, theme.PLAYER_COLORS[owner], layers=4, max_alpha=80
            )
        # 贴图带一圈描边，比 ``2*radius`` 略大 —— 所以按**中心**摆，
        # 不能再用 ``cx - radius``。
        surface.blit(image, image.get_rect(center=(cx, cy)))
        if kind == "queen":
            _draw_crown(surface, (cx, cy), radius)
        if active:
            pygame.draw.circle(surface, theme.SELECT_RING, (cx, cy), radius + 2, 2)

    def stack_badge_rect(self, pos: Pos) -> pygame.Rect:
        """叠层数字角标的位置。

        必须留在**本格六边形内**：原先贴在右上方 0.52 / 0.72 倍处，已经探进
        邻格，正好压住邻格的落点提示（"提示点被压住"的一半原因就是它）。
        """
        cx, cy = self.cell_center(pos)
        radius = max(7, int(self.hex_px() * 0.21))
        badge = pygame.Rect(0, 0, radius * 2, radius * 2)
        badge.center = (int(cx + self.hex_px() * 0.36), int(cy - self.hex_px() * 0.50))
        return badge

    def _draw_stack_badge(
        self, surface: pygame.Surface, fonts: FontBook, pos: Pos, height: int
    ) -> None:
        """叠层角标：甲虫压住别人时给个数字，不然完全看不出这格有几枚。"""
        badge = self.stack_badge_rect(pos)
        render.rounded_rect(surface, badge, theme.SHADOW, badge.width // 2)
        render.rounded_rect(surface, badge, theme.WARN, badge.width // 2, 1)
        render.text(
            surface, fonts.get(max(9, badge.width // 2)), str(height),
            badge.center, theme.WARN, align="center", baseline="middle",
        )

    # ------------------------------------------------------------------ #
    # 手牌条
    # ------------------------------------------------------------------ #

    def _card_at(self, pos: tuple[int, int]) -> str | None:
        for kind, rect in self._cards.items():
            if rect.collidepoint(pos):
                return kind
        return None

    def _layout_cards(self, state: HiveState, player: int) -> None:
        """排手牌卡。

        三条自适应规则，为的是"窄窗口 / 矮窗口下不挤成一团"：

        1. 卡片高度跟着手牌条高度走（矮窗口下 62px 的卡片塞不进 60px 的条）；
        2. 宽度不够时**先让掉**右边的双方余量胶囊、再让掉左边的「手牌」标签，
           最后才压缩卡片 —— 卡片是唯一能点的地方，绝不先牺牲它；
        3. 卡片宽度留了下限，免得 8 张扩展卡在窄窗口里压成一条线。
        """
        kinds = active_kinds(state.expansion)
        count = len(kinds)
        self._show_hand_label = self.hand_rect.width >= LABEL_MIN_WIDTH
        self._show_hand_chip = self.hand_rect.width >= CHIP_MIN_WIDTH
        card_h = max(30, min(CARD_H, self.hand_rect.height - 12))
        left = self.hand_rect.x + HAND_PAD + (HAND_LABEL_W if self._show_hand_label else 0)
        right = self.hand_rect.right - HAND_PAD - (CHIP_W if self._show_hand_chip else 0)
        span = max(1, right - left - CARD_GAP * (count - 1))
        card_w = max(CARD_MIN_W, min(CARD_W, span // max(1, count)))
        top = self.hand_rect.y + (self.hand_rect.height - card_h) // 2
        self._cards = {}
        for i, kind in enumerate(kinds):
            self._cards[kind] = pygame.Rect(
                left + i * (card_w + CARD_GAP), top, card_w, card_h
            )

    def _draw_hand(
        self, surface: pygame.Surface, fonts: FontBook, state: HiveState,
        interactive: bool, view: ViewState,
    ) -> None:
        player = self._hand_player(view)
        self._layout_cards(state, player)

        render.rounded_rect(
            surface, self.hand_rect.inflate(-4, -6), theme.PANEL, theme.RADIUS
        )
        render.rounded_rect(
            surface, self.hand_rect.inflate(-4, -6), theme.BORDER_SOFT, theme.RADIUS, 1
        )

        label_font = fonts.get(12)
        # 卡片显示的是"我方"的手牌：双人 / 自对弈跟随当前行动方（轮到谁画谁的），
        # 人机对战钉在人类那一方（见 _hand_player）。
        # 标签放最左边的窄条里，垂直居中 —— 和卡片同高会被卡片整块盖住。
        # 窗口太窄时先让掉它：卡片是唯一能点的地方。
        if self._show_hand_label:
            render.text(
                surface, label_font, "手牌",
                (self.hand_rect.x + HAND_PAD + HAND_LABEL_W // 2, self.hand_rect.centery),
                theme.TEXT_DIM if interactive else theme.TEXT_FAINT,
                align="center", baseline="middle",
            )

        for index, (kind, rect) in enumerate(self._cards.items()):
            left = state.hand_left(player, kind)
            self._draw_card(surface, fonts, kind, left, rect, player, interactive, index)

        # 右上角报**双方**余量（昆虫棋里"还剩几只甲虫"是公开信息）。
        # 用玩家号而不是"我 / 对手"：自对弈时两边都是 AI，"我"没人可指。
        if self._show_hand_chip:
            chip = pygame.Rect(0, 0, CHIP_W, 24)
            chip.topright = (self.hand_rect.right - HAND_PAD, self.hand_rect.y + 10)
            render.rounded_rect(surface, chip, theme.PANEL_ALT, theme.RADIUS_SM)
            render.text(
                surface, label_font,
                f"玩家1 {state.hand_total(0)} · 玩家2 {state.hand_total(1)}",
                chip.center, theme.TEXT_DIM, align="center", baseline="middle",
            )

    def _draw_card(
        self,
        surface: pygame.Surface,
        fonts: FontBook,
        kind: str,
        left: int,
        rect: pygame.Rect,
        player: int,
        interactive: bool,
        index: int = 0,
    ) -> None:
        empty = left <= 0
        picked = self._picked == kind
        hovered = self._hover_card == kind and not empty and interactive

        if picked:
            render.rounded_rect(surface, rect, theme.ACCENT_DIM, theme.RADIUS_SM)
        elif hovered:
            render.rounded_rect(surface, rect, theme.PANEL_HOVER, theme.RADIUS_SM)
        else:
            render.rounded_rect(surface, rect, theme.PANEL_ALT, theme.RADIUS_SM)
        render.rounded_rect(
            surface, rect,
            theme.ACCENT if picked else (theme.BORDER if not empty else theme.BORDER_SOFT),
            theme.RADIUS_SM, 2 if picked else 1,
        )
        # 卡片底边一道虫种色 —— 和棋子上那圈镶边同色，两边对得上号
        stripe = pygame.Rect(rect.x + 4, rect.bottom - 4, rect.width - 8, 2)
        if stripe.width > 0:
            render.rounded_rect(
                surface, stripe,
                kind_tint(kind) if not empty else theme.mix(kind_tint(kind), theme.PANEL, 0.7),
                1,
            )

        radius = max(8, min(rect.width // 2 - 6, (rect.height - 26) // 2))
        image = sprite(kind, player, radius)
        if empty:
            faded = image.copy()
            faded.fill((255, 255, 255, 70), special_flags=pygame.BLEND_RGBA_MULT)
            image = faded
        surface.blit(image, image.get_rect(midtop=(rect.centerx, rect.y + 4)))

        render.text(
            surface, fonts.get(11), KIND_LABELS.get(kind, kind),
            (rect.centerx, rect.bottom - 12),
            theme.TEXT if not empty else theme.TEXT_FAINT,
            align="center", baseline="middle",
        )

        # 左上角是**数字键**提示：键盘 1..8 直接选这张卡（不用把鼠标甩到底部）
        if rect.width >= 34 and not empty:
            render.text(
                surface, fonts.get(9), str(index + 1),
                (rect.x + 4, rect.y + 3), theme.TEXT_FAINT,
            )

        # 数量角标：只有 >1 才画（1 枚时角标纯属噪音）
        if left > 1:
            badge = pygame.Rect(0, 0, 20, 16)
            badge.topright = (rect.right - 3, rect.y + 3)
            render.rounded_rect(surface, badge, theme.SHADOW, 4)
            render.text(
                surface, fonts.get(10), str(left), badge.center,
                theme.WARN, align="center", baseline="middle",
            )

    def _draw_scale_chip(self, surface: pygame.Surface, fonts: FontBook) -> None:
        """左下角的缩放比例 —— 缩放到极端时给个参照，不然玩家会以为卡住了。

        放**左下**而不是右下：底部操作提示是整行居中的长句子，右下角跟它重叠。
        """
        text = f"{self.camera.scale * 100:.0f}%"
        font = fonts.get(11)
        width = font.size(text)[0] + 18
        chip = pygame.Rect(0, 0, width, 22)
        chip.bottomleft = (self.canvas.left + 10, self.canvas.bottom - 10)
        render.rounded_rect(surface, chip, (*theme.PANEL, 210), theme.RADIUS_SM)
        render.text(
            surface, font, text, chip.center, theme.TEXT_FAINT,
            align="center", baseline="middle",
        )


def _draw_crown(surface: pygame.Surface, center: tuple[int, int], radius: int) -> None:
    """蜂后头上的一顶金色小皇冠。

    为什么不是"再画一圈环"：白色圆环已经有两个含义（选中 / 最后一手），
    再叠一个就完全分不清了；而且昆虫的贴图**没有填满**外接方框（蜜蜂又扁又宽），
    按贴图尺寸画的环常常落在虫子身体外面，看着像选中框。
    """
    cx, cy = center
    width = max(5.0, radius * 0.56)
    height = max(4.0, radius * 0.42)
    top = cy - radius * 0.94
    points = [
        (int(cx), int(top)),
        (int(cx + width / 2), int(top + height)),
        (int(cx - width / 2), int(top + height)),
    ]
    pygame.draw.polygon(surface, theme.SHADOW, points, 3)
    pygame.draw.polygon(surface, theme.WARN, points)


def make_view() -> HiveView:
    """视图工厂（注册表用）。"""
    return HiveView()


__all__ = ["HiveView", "make_view"]
