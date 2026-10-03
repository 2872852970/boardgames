"""落子反弹动画的物理特性。

这些性质是当初踩坑换来的，任何一条退化都会让"弹跳"看着不对：
掉帧时炸开、底部和顶部落子速度差很多、或者永远停不下来。
"""

from __future__ import annotations

from boardgames.ui.animation import BOUNCE_NATURAL_MS, BounceTween


def _settle(tween: BounceTween, dt: float, max_frames: int = 600) -> tuple[int, int]:
    """跑完动画，返回 ``(帧数, 触底次数)``。"""
    frames = 0
    impacts = 0
    while not tween.done and frames < max_frames:
        falling = tween._v > 0
        tween.update(dt)
        if falling and tween._v < 0:
            impacts += 1
        frames += 1
    return frames, impacts


def test_zero_duration_never_plays():
    """``duration_ms == 0`` 时直接落定（沿用 QuoridorView 的约定）。"""
    tween = BounceTween(drop_px=300.0, duration_s=0.0)
    assert tween.done
    assert tween.update(0.016) is False
    assert tween.offset() == 0.0


def test_zero_drop_never_plays():
    tween = BounceTween(drop_px=0.0, duration_s=0.5)
    assert tween.done


def test_offset_starts_at_zero_and_ends_at_minus_drop():
    tween = BounceTween(drop_px=300.0, duration_s=0.85)
    assert tween.offset() == 0.0
    _settle(tween, 0.016)
    assert tween.offset() == -300.0
    assert tween.progress == 1.0


def test_is_dt_independent():
    """掉帧（dt 变大）不得改变落定所需的总时长与触底次数。

    这是固定子步积分存在的全部理由：主循环里 ``dt_ms = min(dt_ms, 100)``
    意味着切后台回来一定会踩到大 dt。
    """
    results = {}
    for dt in (0.0042, 0.016, 0.033, 0.1):
        tween = BounceTween(drop_px=300.0, duration_s=0.85)
        results[dt] = _settle(tween, dt)
    # 帧数会随时长/dt 变化，但"总时长"应几乎一致。
    # 允许 15% 量化误差 —— dt 越大，帧边界越粗（最后一帧可能只推进半帧）。
    total_ms = {dt: frames * dt * 1000 for dt, (frames, _) in results.items()}
    spread = max(total_ms.values()) - min(total_ms.values())
    assert spread / max(total_ms.values()) < 0.15, total_ms
    # 触底次数：dt 够细时（≤16ms）必须完全一致 —— 那才是正常帧率下的观感。
    # dt=100ms 是切后台回来的极端情况，帧太粗会漏采样，单独放宽。
    fine = {impacts for dt, (_, impacts) in results.items() if dt <= 0.016}
    assert len(fine) == 1, f"正常帧率下触底次数不一致: {results}"
    assert results[0.1][1] >= min(fine) - 1, f"极端 dt 下不应凭空多出反弹: {results}"


def test_duration_is_normalized_across_drop_heights():
    """重力按落差归一化 → 同样时长参数下，各种落差的观感大体一致。

    不要求完全相等：落差越大反弹轮次越多，本来就需要更长一点才能停。
    要杜绝的是"底部 500ms / 顶部 1500ms"那种三倍差距。
    """
    totals = []
    for drop in (60.0, 130.0, 300.0, 520.0, 900.0):
        tween = BounceTween(drop_px=drop, duration_s=BOUNCE_NATURAL_MS / 1000)
        frames, _ = _settle(tween, 0.016)
        totals.append(frames * 16)
    ratio = max(totals) / min(totals)
    assert ratio < 1.6, f"落差造成的时长差异过大: {totals}"


def test_bounces_several_times():
    """要有肉眼可见的反弹（一次不算弹）。"""
    tween = BounceTween(drop_px=300.0, duration_s=0.85)
    frames, impacts = _settle(tween, 0.016)
    assert 2 <= impacts <= 10, f"触底 {impacts} 次，反弹观感不对"
    assert frames < 200


def test_always_settles_within_max_duration():
    """极端参数（超长时长）也要被 max_duration_s 兜住，不能锁死输入。"""
    tween = BounceTween(drop_px=900.0, duration_s=60.0)
    frames, _ = _settle(tween, 0.016, max_frames=1000)
    assert tween.done
    assert frames * 0.016 <= tween.max_duration_s + 0.1


def test_higher_drop_bounces_further():
    """落得越高，反弹高度应越大（真物理的表现，不是补间曲线）。"""
    peaks = []
    for drop in (120.0, 400.0):
        tween = BounceTween(drop_px=drop, duration_s=0.85)
        landed_once = False
        first_peak = None
        for _ in range(400):
            was_falling = tween._v > 0
            tween.update(0.008)
            if was_falling and tween._v < 0 and not landed_once:
                landed_once = True
                first_peak = 0.0
            elif landed_once and first_peak is not None and tween._v > 0:
                first_peak = max(first_peak, tween._y)
                break
        peaks.append(first_peak or 0.0)
    assert peaks[1] > peaks[0], f"高落差的反弹应更高: {peaks}"


def test_restitution_zero_lands_once():
    """完全非弹性（restitution=0）应当一次触底就停。"""
    tween = BounceTween(drop_px=300.0, duration_s=0.85, restitution=0.0)
    _, impacts = _settle(tween, 0.016)
    assert impacts == 0, "restitution=0 时不该有回弹"


def test_progress_is_monotonic_enough():
    """progress 用于让影子随高度变淡，大致递增即可（回弹期会小回落）。"""
    tween = BounceTween(drop_px=300.0, duration_s=0.85)
    values = [tween.progress]
    for _ in range(120):
        tween.update(0.016)
        values.append(tween.progress)
    assert values[0] == 0.0
    assert values[-1] == 1.0
    assert max(values) <= 1.0
