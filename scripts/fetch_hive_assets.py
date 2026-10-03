"""一次性抓取昆虫棋的棋子素材：下载 ~ 白模化 ~ 光栅化。

产物写在 ``src/boardgames/games/hive/assets/``，运行时直接读盘，**不联网**。

为什么不用 Pillow / cairosvg
----------------------------
项目只依赖 pygame-ce，而这个脚本只需要"下载 PNG + 抠 alpha + 缩放"，
pygame 全都能做。多引一个原生依赖（cairosvg 在 Windows 上要 cairo DLL）
只为一次性脚本很不划算。

素材来源
--------
`OpenMoji <https://openmoji.org>`_，许可 **CC0 1.0**。

取的是 **color 变体**的 alpha 通道：彩色版的图案是实心填充，alpha 覆盖率
13%~27%，抠出来就是一枚饱满的剪影；而 ``black`` 变体是 2px 描边的线稿
（覆盖率只有 7%~13%），缩到棋子尺寸会细得看不清。

GitHub raw 在部分网络环境下不通，所以统一走 jsdelivr 的 ``/gh/`` 代理。

用法::

    uv run python scripts/fetch_hive_assets.py            # 缺哪个补哪个
    uv run python scripts/fetch_hive_assets.py --force    # 全部重新下载
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

#: 输出尺寸（棋子最大也就 110px 的外接圆，192 足够，再大纯属浪费）
OUTPUT_SIZE = 192
#: 裁掉四周空白后留的余量（占边长的比例）
PAD_RATIO = 0.06
#: 单张下载超时（秒）
TIMEOUT = 30

#: 虫种 -> (OpenMoji code point, 中文名, 说明)
PIECES: tuple[tuple[str, str, str, str], ...] = (
    ("queen", "1F41D", "蜂后", "蜜蜂 🐝"),
    ("beetle", "1FAB2", "甲虫", "甲虫 🪲"),
    ("grasshopper", "1F997", "蚱蜢", "蟋蟀 🦗（蚱蜢无独立 emoji，用同目昆虫代替）"),
    ("spider", "1F577", "蜘蛛", "蜘蛛 🕷"),
    ("ant", "1F41C", "兵蚁", "蚂蚁 🐜"),
    ("ladybug", "1F41E", "瓢虫", "瓢虫 🐞"),
    ("mosquito", "1F99F", "蚊子", "蚊子 🦟"),
    ("pillbug", "1FAB3", "鼠妇", "蟑螂 🪳（鼠妇无 emoji，用体型最接近的代替）"),
)

#: jsdelivr 的多个边缘节点。主站被限流时会整段 TLS 被掐断
#: （``SSL: UNEXPECTED_EOF_WHILE_READING``），换一个节点通常就好了。
MIRRORS: tuple[str, ...] = (
    "https://cdn.jsdelivr.net/gh/hfg-gmuend/openmoji@master",
    "https://gcore.jsdelivr.net/gh/hfg-gmuend/openmoji@master",
    "https://testingcf.jsdelivr.net/gh/hfg-gmuend/openmoji@master",
    "https://fastly.jsdelivr.net/gh/hfg-gmuend/openmoji@master",
)

_ASSET_DIR = Path(__file__).resolve().parent.parent / "src" / "boardgames" / "games" / "hive" / "assets"


def _urls(code: str) -> list[str]:
    """按优先级排列的候选 URL。

    首选 **color 变体**（实心填充，抠出来是饱满剪影）；退而求其次用 black
    变体当剪影（线稿，偏细，但至少能加载）。注意别退到 SVG —— pygame 解不了。
    每个变体都在所有镜像上试一遍 —— 单看某个镜像挂掉不代表源不可用。
    """
    variants = (f"color/618x618/{code}.png", f"black/618x618/{code}.png")
    return [f"{mirror}/{variant}" for variant in variants for mirror in MIRRORS]


def _detail_urls(code: str) -> list[str]:
    """线稿细节（轮廓 + 斑点 + 体节）的候选 URL。"""
    return [f"{mirror}/black/618x618/{code}.png" for mirror in MIRRORS]


def _download(url: str, attempts: int = 2) -> bytes | None:
    """下载一个 URL，失败退避重试。

    jsdelivr 在连续请求下偶发 ``SSL: UNEXPECTED_EOF_WHILE_READING``（限流），
    单次失败不代表源不可用，所以必须重试。
    """
    import time

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "boardgames/1.0"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == attempts:
                print(f"    下载失败 {url} -> {exc}")
                return None
            time.sleep(0.6 * attempt)


def _init_pygame() -> None:
    """``convert_alpha()`` 没有 display 会抛 ``No convert format has been set``。"""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    if not pygame.get_init():
        pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))


def _crop_box(masks: list) -> tuple[int, int, int, int] | None:
    """多张 mask 的包围盒**并集**，四周留 :data:`PAD_RATIO` 余量。"""
    boxes = [box for mask in masks for box in mask.get_bounding_rects()]
    if not boxes:
        return None
    # 多块 bounding rect 时取并集（昆虫的触角/腿可能与身体分离）
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.right for box in boxes)
    bottom = max(box.bottom for box in boxes)
    pad = int(max(right - left, bottom - top) * PAD_RATIO)
    return (max(0, left - pad), max(0, top - pad), right + pad, bottom + pad)


def _square_from(mask, crop: tuple[int, int, int, int]) -> object:
    """把 mask 按 ``crop`` 裁成正方形、居中、缩放到 :data:`OUTPUT_SIZE`。"""
    import pygame

    left, top, right, bottom = crop
    width, height = right - left, bottom - top
    side = max(width, height)
    square = pygame.Surface((side, side), pygame.SRCALPHA)
    square.blit(
        mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)),
        ((side - width) // 2, (side - height) // 2),
        pygame.Rect(left, top, width, height),
    )
    return pygame.transform.smoothscale(square, (OUTPUT_SIZE, OUTPUT_SIZE))


def _make_molds(payloads: list[bytes]) -> list[object]:
    """下载到的 PNG bytes（color / black 各一张）-> 共用裁剪框的白模 Surface。

    白模（RGB 恒为白、alpha 保留轮廓）是运行时着色的前提：``fill(玩家色)``
    再 ``BLEND_RGBA_MULT`` 一行就能把整枚棋子染成玩家色。

    抠轮廓用 :meth:`pygame.mask.Mask.from_surface`（``threshold=1`` —— 任何
    alpha > 0 的像素都算轮廓内）。mask 得到的是**二值** alpha，抗锯齿会丢；
    但 618 -> 192 的 3.2 倍 ``smoothscale`` 降采样会把边缘重新平均成半透明，
    视觉上仍然平滑。

    两张图**共用同一个裁剪框** —— 只有它们本来就对齐（OpenMoji 的 color 与
    black 变体共用同一个 72 视框与 618 画布），叠起来才不会有偏移。
    """
    import pygame

    images = [pygame.image.load(io.BytesIO(raw), "png").convert_alpha() for raw in payloads]
    masks = [pygame.mask.from_surface(image, 1) for image in images]
    crop = _crop_box(masks)
    if crop is None:
        raise ValueError("图片是完全透明的，抠不出轮廓")
    return [_square_from(mask, crop) for mask in masks]


def _write_credits(day: str) -> None:
    rows = "\n".join(
        f"| `{kind}.png` / `{kind}.line.png` | {name} | {code} | {note} |"
        for kind, code, name, note in PIECES
    )
    text = f"""# 昆虫棋棋子素材

来源：**[OpenMoji](https://openmoji.org)** —— 许可 **CC0 1.0**（公有领域贡献）。
获取日期：{day}。

每个虫种两个文件：

* ``<kind>.png`` —— **实心剪影**，取自 OpenMoji **color** 变体的 alpha 通道；
* ``<kind>.line.png`` —— **线稿细节**（轮廓 + 斑点 + 体节），取自 **black** 变体。

运行时的画法是：剪影染成玩家亮色当底，线稿染成玩家深色叠在上面 ——
于是得到"扁平填色 + 深色描边细节"的棋子，与木质棋子的观感接近。

## 清单

| 文件 | 虫种 | code point | 备注 |
|---|---|---|---|
{rows}

## 处理流程

`scripts/fetch_hive_assets.py`：

1. 下载 OpenMoji **color** 与 **black** 变体的 618×618 PNG（走 jsdelivr 的
   `/gh/` 代理，因为 `raw.githubusercontent.com` 在部分网络环境下不通）；
2. 用 `pygame.mask` 抠出 alpha 通道 → **纯白模**（RGB 恒为 255，alpha 保留轮廓）；
   两张图**共用同一个裁剪框**，保证叠加不偏移；
3. 裁掉四周空白，四周留 6% 余量，居中成正方形；
4. `smoothscale` 到 {OUTPUT_SIZE}×{OUTPUT_SIZE}（3.2× 降采样把二值边缘重新平均成抗锯齿）。

白模化是运行时着色的前提：视图里 `fill(玩家色)` 再 `BLEND_RGBA_MULT` 一行
就能把整枚棋子染成玩家色。

## 兜底

素材缺失时（比如没跑过这个脚本、或者离线环境），`HiveView` 里的
`_Sprites._fallback()` 会用 `pygame.draw` 现画一枚可区分的虫形，
游戏与测试都能正常跑。
"""
    (_ASSET_DIR / "CREDITS.md").write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载并光栅化昆虫棋棋子素材")
    parser.add_argument("--force", action="store_true", help="已存在的文件也重新下载")
    args = parser.parse_args(argv)

    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    _init_pygame()
    import pygame

    failed: list[str] = []
    for kind, code, name, _note in PIECES:
        base_path = _ASSET_DIR / f"{kind}.png"
        line_path = _ASSET_DIR / f"{kind}.line.png"
        if base_path.exists() and line_path.exists() and not args.force:
            print(f"  跳过 {kind}（已存在，用 --force 重新下载）")
            continue

        payloads: list[bytes] = []
        for url in _urls(code):
            payload = _download(url)
            if payload is not None:
                print(f"  {kind} <- {url}")
                payloads.append(payload)
                break
        if not payloads:
            print(f"  !! {kind}（{name}）剪影源失败，稍后走程序绘制兜底")
            failed.append(kind)
            continue

        detail = None
        for url in _detail_urls(code):
            detail = _download(url)
            if detail is not None:
                print(f"  {kind} 细节 <- {url}")
                break
        if detail is None:
            print(f"  .. {kind} 拿不到线稿细节，只做纯色棋子")
        else:
            payloads.append(detail)

        try:
            molds = _make_molds(payloads)
        except (pygame.error, ValueError) as exc:
            print(f"  !! {kind} 处理失败: {exc}")
            failed.append(kind)
            continue

        pygame.image.save(molds[0], str(base_path))
        print(f"  -> {base_path.name}")
        if len(molds) > 1:
            pygame.image.save(molds[1], str(line_path))
            print(f"  -> {line_path.name}")
        else:
            line_path.unlink(missing_ok=True)

    _write_credits(_dt.date.today().isoformat())

    if failed:
        print(f"\n完成，但 {len(failed)} 个虫种没拿到素材：{', '.join(failed)}")
        print("运行时会对这些虫种走程序绘制兜底，不影响游戏与测试。")
        return 0
    print(f"\n全部 {len(PIECES)} 枚素材就绪 -> {_ASSET_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
