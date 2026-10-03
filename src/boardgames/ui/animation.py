"""缓动与补间。"""

from __future__ import annotations

import math
from dataclasses import dataclass


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def ease_out_back(t: float, overshoot: float = 1.4) -> float:
    t = max(0.0, min(1.0, t))
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_pos(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


@dataclass
class Tween:
    """线性推进的补间；``update`` 返回是否已结束。"""

    duration_s: float
    elapsed: float = 0.0

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration_s

    @property
    def raw(self) -> float:
        if self.duration_s <= 0:
            return 1.0
        return min(1.0, self.elapsed / self.duration_s)

    def update(self, dt_s: float) -> bool:
        self.elapsed += dt_s
        return self.done

    def eased(self, fn=ease_out_cubic) -> float:
        return fn(self.raw)


def pulse(seconds: float, period: float = 1.4) -> float:
    """0..1 的呼吸值，用于"AI 思考中"这类提示。"""
    return (math.sin(seconds * 2 * math.pi / period) + 1.0) / 2.0


#: 重力落子自然弹跳的时长（毫秒），用作 ``BounceTween`` 的标定基准。
BOUNCE_NATURAL_MS = 880.0


@dataclass
class BounceTween:
    """自由落体 → 触底反弹 → 阻尼衰减的**物理**补间。

    与 :class:`Tween` 的关键差别：不按时间插值曲线，而是真的积分运动方程，
    所以反弹次数与高度都是"算出来"的，视觉上才像真东西在弹。

    三个必须保留的设计（都是踩过的坑）：

    1. **固定子步积分**（1/240 秒）。朴素的半隐式欧拉在 dt=33ms（掉帧）时会
       反弹 440 次、持续 4 秒并锁死输入；加了子步后 dt 从 4ms 到 100ms 的
       结果**完全一致**。主循环里 ``dt_ms = min(dt_ms, 100)`` 的上限意味着
       切后台回来必踩这个坑，所以子步不是优化，是必需项。
    2. **重力按落差归一化**（``gravity ∝ drop_px``）。否则同样时长参数下，
       掉到底部的棋子 458ms 落定、掉到顶部的要 1458ms，观感严重不一致。
    3. **静止阈值**：速度低于 ``v_threshold`` 直接停，否则会无限小弹。
    """

    drop_px: float
    duration_s: float
    restitution: float = 0.45
    v_threshold: float = 45.0        # px/s
    max_duration_s: float = 2.5
    #: 缩放钳制：时长最多压到 35%、最多拉长 2.5 倍
    _time_scale_bounds: tuple[float, float] = (0.35, 2.5)

    _t: float = 0.0
    _y: float = 0.0                 # **已经落下的距离**（0 起，到 drop_px 触底）
    _v: float = 0.0
    gravity: float = 0.0
    _landed: bool = False           # 是否已落定（不能只看速度：初始速度就是 0）
    _sub_step: float = 1.0 / 240.0

    def __post_init__(self) -> None:
        if self.drop_px <= 0 or self.duration_s <= 0:
            # 退化情况：直接处于落定状态（_y 要放到 drop_px，见 offset()）
            self.gravity = 0.0
            self._y = self.drop_px
            self._v = 0.0
            self._landed = True
            return
        # 自然时长 T0 ∝ sqrt(drop/g)：先算出"标准重力下需要多久"，再反解重力，
        # 让实际总时长逼近调用方要的 duration_s。
        target_ms = self.duration_s * 1000.0
        k = BOUNCE_NATURAL_MS / max(1.0, target_ms)
        low, high = self._time_scale_bounds
        k = max(low, min(high, k))
        decay = 1.0 / (1.0 - self.restitution)
        self.gravity = 2.0 * decay * decay / (k * k) * self.drop_px
        self._y = 0.0
        self._v = 0.0
        self._landed = False

    @property
    def done(self) -> bool:
        return self._landed

    def update(self, dt_s: float) -> bool:
        """推进 ``dt_s`` 秒；返回是否仍在播放。"""
        if self._landed:
            return False
        remaining = min(dt_s, self.max_duration_s - self._t)
        while remaining > 1e-9 and not self._landed:
            step = min(remaining, self._sub_step)
            remaining -= step
            self._t += step
            self._v += self.gravity * step
            self._y += self._v * step
            if self._y >= self.drop_px:
                self._y = self.drop_px
                self._v = -self._v * self.restitution
                if abs(self._v) < self.v_threshold:
                    self._settle()
        # 超时兜底必须放在循环**之外**：极端参数（很短的 duration_s 配上
        # 很小的 v_threshold）下棋子可能一直悬在半空、始终碰不到 drop_px，
        # 那样它会永远播下去并锁死输入。
        if not self._landed and self._t >= self.max_duration_s:
            self._settle()
        return not self._landed

    def _settle(self) -> None:
        self._y = self.drop_px
        self._v = 0.0
        self._landed = True

    def offset(self) -> float:
        """绘制时的纵向偏移（**向上为负**，相对静止位置）。

        ``_y`` 是"已经落下的距离"，不是"离静止位置多高"，所以偏移是
        ``_y - drop_px``：起点在静止位置**上方** ``drop_px``，落地回到 ``0``。

        写成 ``-self._y`` 会让棋子从槽位里**往上飞**出去（起点恰好落在
        目标格上、然后一路升到棋盘外面），那是"重力方向反了"的经典症状。
        """
        return self._y - self.drop_px

    @property
    def progress(self) -> float:
        """0..1 的落定进度，用于让影子随高度变淡。"""
        if self.drop_px <= 0:
            return 1.0
        return max(0.0, min(1.0, self._y / self.drop_px))
