"""昆虫棋的棋子定义：虫种常量、配额、中文名、素材文件名。

**纯数据**，不碰 pygame —— 素材文件名只是字符串，真正的加载与着色在
``view.py`` 里做（本包只有 ``view.py`` 允许 import pygame）。
"""

from __future__ import annotations

from typing import NamedTuple

#: 虫种标识
QUEEN = "queen"
BEETLE = "beetle"
GRASSHOPPER = "grasshopper"
SPIDER = "spider"
ANT = "ant"
LADYBUG = "ladybug"
MOSQUITO = "mosquito"
PILLBUG = "pillbug"

#: 基础五虫（规则页所用的棋子套装）
BASE_KINDS: tuple[str, ...] = (QUEEN, BEETLE, GRASSHOPPER, SPIDER, ANT)
#: 官方扩展三虫
EXTRA_KINDS: tuple[str, ...] = (LADYBUG, MOSQUITO, PILLBUG)
#: 全部虫种（顺序 = 手牌条与侧栏的显示顺序）
ALL_KINDS: tuple[str, ...] = BASE_KINDS + EXTRA_KINDS

#: 每方每种虫的枚数（基础套装，合计 11）
BASE_COUNTS: dict[str, int] = {
    QUEEN: 1,
    BEETLE: 2,
    GRASSHOPPER: 3,
    SPIDER: 2,
    ANT: 3,
}
#: 扩展虫的枚数（合计 3）
EXTRA_COUNTS: dict[str, int] = {LADYBUG: 1, MOSQUITO: 1, PILLBUG: 1}

#: 中文名（界面显示）
KIND_LABELS: dict[str, str] = {
    QUEEN: "蜂后",
    BEETLE: "甲虫",
    GRASSHOPPER: "蚱蜢",
    SPIDER: "蜘蛛",
    ANT: "兵蚁",
    LADYBUG: "瓢虫",
    MOSQUITO: "蚊子",
    PILLBUG: "鼠妇",
}

#: 一句话走法说明（悬停提示 / 规则说明用）
KIND_HINTS: dict[str, str] = {
    QUEEN: "沿蜂巢外缘滑动一格",
    BEETLE: "走一格，可以爬到相邻的棋上面，也可以从棋堆上下来",
    GRASSHOPPER: "沿一个方向直线跳过至少一枚棋，落在第一个空格",
    SPIDER: "恰好滑动三格，不能重复经过任何一格",
    ANT: "沿蜂巢外缘滑动任意距离",
    LADYBUG: "先爬到相邻的棋上，再落到下一格空地",
    MOSQUITO: "模仿任一相邻棋子（含被压住的那枚）的走法",
    PILLBUG: "走一格；也可以把一枚相邻的棋搬到自己的邻格",
}

#: 每个虫种的**专属色调**。
#:
#: 素材全是 OpenMoji 的昆虫图标，缩到棋子尺寸后彼此很像；染色时又只按玩家色
#: 染，于是"这一枚是甲虫还是蜘蛛"完全看不出来。给每个虫种一个色相之后，
#: 棋盘上一眼就能分辨虫种 —— **敌我仍然靠玩家色**（亮色身体），所以两者
#: 不打架：身体是"谁的"，外圈镶边与线稿是"什么虫"。
#:
#: 全部是**纯数据**（RGB 元组），本模块不 import pygame —— 真正的混合在
#: ``view.py`` 里做（那里才知道玩家调色板）。
KIND_TINTS: dict[str, tuple[int, int, int]] = {
    QUEEN: (255, 208, 110),  # 金 —— 与头顶那顶皇冠同色系
    BEETLE: (150, 172, 218),  # 钢青
    GRASSHOPPER: (128, 224, 116),  # 草绿
    SPIDER: (200, 130, 245),  # 紫罗兰
    ANT: (198, 96, 62),  # 赭棕（刻意压暗压红 —— 亮橙会和瓢虫撞色）
    LADYBUG: (244, 70, 96),  # 樱桃红
    MOSQUITO: (86, 218, 206),  # 青碧
    PILLBUG: (132, 146, 168),  # 深石板（米灰会和蜂后撞色）
}



class Piece(NamedTuple):
    """场上的一枚棋子。

    ``owner`` 是**玩家号 0/1**（不是棋子值 1/2）—— 调色板 ``theme.PLAYER_COLORS``
    只有两项，用棋子值当索引会直接 ``IndexError``。
    """

    owner: int
    kind: str

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


def counts(expansion: bool = False) -> dict[str, int]:
    """本局每种虫的枚数（``expansion=True`` 时带上瓢虫 / 蚊子 / 鼠妇）。"""
    out = dict(BASE_COUNTS)
    if expansion:
        out.update(EXTRA_COUNTS)
    return out


def active_kinds(expansion: bool = False) -> tuple[str, ...]:
    """本局启用的虫种（顺序固定）。"""
    return ALL_KINDS if expansion else BASE_KINDS


def pieces_per_player(expansion: bool = False) -> int:
    """每方总棋子数（基础 11，带扩展 14）。"""
    return sum(counts(expansion).values())
