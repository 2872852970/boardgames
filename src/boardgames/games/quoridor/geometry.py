"""Quoridor 几何：坐标、墙体锚点 ↔ 被阻断的边、邻接与 BFS 最短路径。

坐标约定
--------
* 格子 ``(x, y)``：``x`` 为列（0 左 → size-1 右），``y`` 为行（0 上 → size-1 下）。
* 玩家 0 起点在 ``(mid, size-1)``（下底中央），目标行 ``y == 0``。
* 玩家 1 起点在 ``(mid, 0)``（上底中央），目标行 ``y == size-1``。

墙体表示
--------
墙长 2 格，用**锚点**表示（锚点网格为 ``(size-1) × (size-1)``，记 ``w = size-1``）:

* 水平墙 ``("h", ax, ay)``：压在水平网格线 ``y = ay+1`` 上，横跨 ``x ∈ [ax, ax+2]``。
  它阻断两条**竖直边** ``(ax, ay)`` 与 ``(ax+1, ay)``，即阻断上下移动。
* 垂直墙 ``("v", ax, ay)``：压在竖直网格线 ``x = ax+1`` 上，纵跨 ``y ∈ [ay, ay+2]``。
  它阻断两条**水平边** ``(ax, ay)`` 与 ``(ax, ay+1)``，即阻断左右移动。

坑位提示：``h_mask`` / ``v_mask`` 都是 ``w×w`` 位掩码，位序 ``ay * w + ax``。
由锚点派生出的边网格维度是**不同**的：竖直边 ``w × size``，水平边 ``size × w``。
"""

from __future__ import annotations

from collections import deque
from functools import lru_cache

Pos = tuple[int, int]
Wall = tuple[str, int, int]  # (orient, ax, ay)

HORIZONTAL = "h"
VERTICAL = "v"

UP: Pos = (0, -1)
DOWN: Pos = (0, 1)
LEFT: Pos = (-1, 0)
RIGHT: Pos = (1, 0)
ORTHO: tuple[Pos, ...] = (UP, DOWN, LEFT, RIGHT)


# --------------------------------------------------------------------------- #
# 锚点掩码基础操作
# --------------------------------------------------------------------------- #

def anchor_count(size: int) -> int:
    """单方向锚点总数。"""
    return (size - 1) * (size - 1)


def anchor_bit(size: int, ax: int, ay: int) -> int:
    w = size - 1
    return 1 << (ay * w + ax)


def has_anchor(mask: int, size: int, ax: int, ay: int) -> bool:
    w = size - 1
    return bool((mask >> (ay * w + ax)) & 1)


def in_board(size: int, x: int, y: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def in_anchor_grid(size: int, ax: int, ay: int) -> bool:
    w = size - 1
    return 0 <= ax < w and 0 <= ay < w


# --------------------------------------------------------------------------- #
# 边阻断查询（派生自锚点，不冗余存储）
# --------------------------------------------------------------------------- #

def blocked_vertical(size: int, h_mask: int, x: int, y: int) -> bool:
    """从 ``(x, y)`` 走到 ``(x, y+1)`` 是否被阻断。``y`` 需在 ``0..size-2``。"""
    w = size - 1
    if not (0 <= y < w):
        return True
    if x - 1 >= 0 and has_anchor(h_mask, size, x - 1, y):
        return True
    return x <= w - 1 and has_anchor(h_mask, size, x, y)


def blocked_horizontal(size: int, v_mask: int, x: int, y: int) -> bool:
    """从 ``(x, y)`` 走到 ``(x+1, y)`` 是否被阻断。``x`` 需在 ``0..size-2``。"""
    w = size - 1
    if not (0 <= x < w):
        return True
    if y - 1 >= 0 and has_anchor(v_mask, size, x, y - 1):
        return True
    return y <= w - 1 and has_anchor(v_mask, size, x, y)


def can_step(size: int, h_mask: int, v_mask: int, src: Pos, dst: Pos) -> bool:
    """两个**正交相邻**格之间是否可以走通（不含边界检查以外的语义）。"""
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    if (dx, dy) == UP:
        return not blocked_vertical(size, h_mask, src[0], src[1] - 1)
    if (dx, dy) == DOWN:
        return not blocked_vertical(size, h_mask, src[0], src[1])
    if (dx, dy) == LEFT:
        return not blocked_horizontal(size, v_mask, src[0] - 1, src[1])
    if (dx, dy) == RIGHT:
        return not blocked_horizontal(size, v_mask, src[0], src[1])
    return False


# --------------------------------------------------------------------------- #
# 最短路径（BFS）—— 既是放墙合法性判据，也是评估函数的核心
# --------------------------------------------------------------------------- #

def shortest_path(
    size: int, h_mask: int, v_mask: int, start: Pos, goal_row: int
) -> int | None:
    """从 ``start`` 到 ``goal_row`` 任意格的最短步数；不可达返回 ``None``。

    **忽略对方棋子** —— 官方"必须留一条路"的判据只看墙。
    """
    if start[1] == goal_row:
        return 0
    seen = {start}
    frontier = deque([(start, 0)])
    while frontier:
        (x, y), dist = frontier.popleft()
        for dx, dy in ORTHO:
            nx, ny = x + dx, y + dy
            if not in_board(size, nx, ny) or (nx, ny) in seen:
                continue
            if not can_step(size, h_mask, v_mask, (x, y), (nx, ny)):
                continue
            if ny == goal_row:
                return dist + 1
            seen.add((nx, ny))
            frontier.append(((nx, ny), dist + 1))
    return None


def shortest_path_cells(
    size: int, h_mask: int, v_mask: int, start: Pos, goal_row: int
) -> list[Pos] | None:
    """返回一条最短路径的格子序列（含起点与终点），用于生成候选墙位。"""
    if start[1] == goal_row:
        return [start]
    came: dict[Pos, Pos | None] = {start: None}
    frontier = deque([start])
    end: Pos | None = None
    while frontier and end is None:
        cur = frontier.popleft()
        x, y = cur
        for dx, dy in ORTHO:
            nx, ny = x + dx, y + dy
            if not in_board(size, nx, ny) or (nx, ny) in came:
                continue
            if not can_step(size, h_mask, v_mask, cur, (nx, ny)):
                continue
            came[(nx, ny)] = cur
            if ny == goal_row:
                end = (nx, ny)
                break
            frontier.append((nx, ny))
    if end is None:
        return None
    path: list[Pos] = []
    node: Pos | None = end
    while node is not None:
        path.append(node)
        node = came[node]
    path.reverse()
    return path


def distance_field(
    size: int, h_mask: int, v_mask: int, goal_row: int
) -> tuple[int, ...]:
    """多源 BFS：每个格子到 ``goal_row`` 的最短步数（不可达为 ``-1``）。

    rollout 用不起"每走一步重算一条最短路径"—— 直接查距离场在 O(1) 内就能选出
    朝目标推进的一步，因此 rollout 绝不会来回振荡，棋局必然收敛。
    """
    total = size * size
    dist = [-1] * total
    frontier: deque[Pos] = deque()
    for x in range(size):
        dist[goal_row * size + x] = 0
        frontier.append((x, goal_row))
    while frontier:
        x, y = frontier.popleft()
        base = dist[y * size + x]
        for dx, dy in ORTHO:
            nx, ny = x + dx, y + dy
            if not in_board(size, nx, ny):
                continue
            index = ny * size + nx
            if dist[index] != -1:
                continue
            if not can_step(size, h_mask, v_mask, (x, y), (nx, ny)):
                continue
            dist[index] = base + 1
            frontier.append((nx, ny))
    return tuple(dist)


@lru_cache(maxsize=256)
def _distance_field_cached(
    size: int, h_mask: int, v_mask: int, goal_row: int
) -> tuple[int, ...]:
    return distance_field(size, h_mask, v_mask, goal_row)


def distance_to_goal(size: int, h_mask: int, v_mask: int, cell: Pos, goal_row: int) -> int | None:
    """``cell`` 到目标行的最短步数（带缓存；不可达返回 ``None``）。"""
    field = _distance_field_cached(size, h_mask, v_mask, goal_row)
    value = field[cell[1] * size + cell[0]]
    return None if value < 0 else value


def reachable_cells(
    size: int, h_mask: int, v_mask: int, start: Pos, blocked_cells: frozenset[Pos] = frozenset()
) -> int:
    """从 ``start`` 出发可到达的格子数（机动性，用于评估函数）。"""
    seen = {start}
    frontier = deque([start])
    while frontier:
        cur = frontier.popleft()
        x, y = cur
        for dx, dy in ORTHO:
            nx, ny = x + dx, y + dy
            if not in_board(size, nx, ny) or (nx, ny) in seen or (nx, ny) in blocked_cells:
                continue
            if not can_step(size, h_mask, v_mask, cur, (nx, ny)):
                continue
            seen.add((nx, ny))
            frontier.append((nx, ny))
    return len(seen)


# --------------------------------------------------------------------------- #
# 边 ↔ 锚点映射（候选墙裁剪用）
# --------------------------------------------------------------------------- #

#: 边的键：``("down", x, y)`` 表示 ``(x,y) ↔ (x,y+1)``（被水平墙阻断）；
#: ``("right", x, y)`` 表示 ``(x,y) ↔ (x+1,y)``（被垂直墙阻断）。
EdgeKey = tuple[str, int, int]
DOWN_EDGE = "down"
RIGHT_EDGE = "right"


def step_edge_key(src: Pos, dst: Pos) -> EdgeKey:
    """两个正交相邻格之间的边键。"""
    if dst[1] != src[1]:
        return (DOWN_EDGE, src[0], min(src[1], dst[1]))
    return (RIGHT_EDGE, min(src[0], dst[0]), src[1])


def wall_edge_keys(wall: Wall) -> tuple[EdgeKey, EdgeKey]:
    """一面墙阻断的两条边。"""
    orient, ax, ay = wall
    if orient == HORIZONTAL:
        return ((DOWN_EDGE, ax, ay), (DOWN_EDGE, ax + 1, ay))
    return ((RIGHT_EDGE, ax, ay), (RIGHT_EDGE, ax, ay + 1))


def path_edge_keys(path: list[Pos]) -> frozenset[EdgeKey]:
    """一条路径经过的全部边。"""
    return frozenset(step_edge_key(a, b) for a, b in zip(path, path[1:], strict=False))


def anchors_blocking_step(size: int, src: Pos, dst: Pos) -> list[Wall]:
    """能阻断 ``src -> dst`` 这一步的所有墙锚点（最多 2 个）。"""
    out: list[Wall] = []
    if dst[1] != src[1]:  # 上下移动 → 需要水平墙
        edge_y = src[1] if dst[1] > src[1] else src[1] - 1
        for ax in (src[0] - 1, src[0]):
            if in_anchor_grid(size, ax, edge_y):
                out.append((HORIZONTAL, ax, edge_y))
    else:  # 左右移动 → 需要垂直墙
        edge_x = src[0] if dst[0] > src[0] else src[0] - 1
        for ay in (src[1] - 1, src[1]):
            if in_anchor_grid(size, edge_x, ay):
                out.append((VERTICAL, edge_x, ay))
    return out


# --------------------------------------------------------------------------- #
# 放墙的几何合法性
# --------------------------------------------------------------------------- #

def wall_overlaps(size: int, h_mask: int, v_mask: int, wall: Wall) -> bool:
    """同向重叠：同锚点，或左右/上下相邻锚点（共享一段边）。"""
    orient, ax, ay = wall
    if orient == HORIZONTAL:
        return any(
            has_anchor(h_mask, size, a, ay)
            for a in (ax - 1, ax, ax + 1)
            if in_anchor_grid(size, a, ay)
        )
    return any(
        has_anchor(v_mask, size, ax, b)
        for b in (ay - 1, ay, ay + 1)
        if in_anchor_grid(size, ax, b)
    )


def wall_crosses(h_mask: int, v_mask: int, size: int, wall: Wall) -> bool:
    """交叉：同一锚点上存在正交的墙（构成"十"字）。

    端点相接的 L / T 形**合法** —— 因此这里只查同一锚点的反向墙，
    **不能用边网格判断**（边网格会把 T 形误判为交叉）。
    """
    orient, ax, ay = wall
    if orient == HORIZONTAL:
        return has_anchor(v_mask, size, ax, ay)
    return has_anchor(h_mask, size, ax, ay)
