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
