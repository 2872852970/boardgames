"""应用入口：组装注册表、设置与窗口。

框架不在这里写任何游戏规则 —— 新增棋类时只需：

1. 在 ``games/`` 下实现 ``Game`` / ``State`` / ``Move`` / ``BoardView``；
2. 在 :func:`build_registry` 里注册游戏；
3. 在 :func:`register_builtin_views` 里注册它的视图工厂。
"""

from __future__ import annotations

import argparse
import os
import sys

from boardgames.core.registry import GameRegistry, build_default_registry
from boardgames.settings import Settings


def register_builtin_views(registry: GameRegistry) -> None:
    """把各棋类的棋盘视图挂到注册表上（UI 相关的 import 集中在这里）。"""
    from boardgames.games.quoridor.view import make_view

    registry.register_view("quoridor", make_view)


def build_registry() -> GameRegistry:
    registry = build_default_registry()
    register_builtin_views(registry)
    return registry


def build_window(
    settings: Settings | None = None,
    registry: GameRegistry | None = None,
    *,
    window_size: tuple[int, int] | None = None,
    **kwargs,
):
    from boardgames.ui.window import GameWindow

    return GameWindow(
        settings if settings is not None else Settings.load(),
        registry if registry is not None else build_registry(),
        window_size=window_size,
        **kwargs,
    )


def _parse_size(text: str) -> tuple[int, int]:
    """解析 ``1000x640`` 形式的窗口尺寸。"""
    try:
        left, _, right = text.lower().partition("x")
        width, height = int(left), int(right)
    except ValueError:
        raise argparse.ArgumentTypeError(f"窗口尺寸格式应为 宽x高，例如 1000x640（收到 {text!r}）") from None
    if width < 320 or height < 240:
        raise argparse.ArgumentTypeError("窗口尺寸太小")
    return width, height


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="boardgames", description="棋类游戏 · 步步为营")
    parser.add_argument("--headless", action="store_true", help="不打开窗口（用 dummy 视频驱动）")
    parser.add_argument("--frames", type=int, default=None, help="跑固定帧数后自动退出（自检用）")
    parser.add_argument("--mode", choices=("pvp", "pve", "eve"), default=None)
    parser.add_argument("--p1", choices=("human", "minimax", "mcts", "random"), default=None)
    parser.add_argument("--p2", choices=("human", "minimax", "mcts", "random"), default=None)
    parser.add_argument("--size", type=int, default=None, help="棋盘尺寸")
    parser.add_argument("--walls", type=int, default=None, help="每人墙数")
    parser.add_argument("--screenshot", default=None, help="渲染若干帧后截图到指定路径")
    parser.add_argument("--demo", type=int, default=0, help="截图前先按策略走 N 步，方便看中局画面")
    parser.add_argument("--demo-seed", type=int, default=7, help="demo 走子的随机种子")
    parser.add_argument(
        "--window", type=_parse_size, default=None, help="强制窗口尺寸，如 1000x640（用于验证布局）"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    settings = Settings.load()
    # 命令行覆盖只影响本次运行，不写回配置文件
    overrides = {
        "mode": args.mode,
        "p1_type": args.p1,
        "p2_type": args.p2,
        "board_size": args.size,
        "walls_per_player": args.walls,
    }
    for key, value in overrides.items():
        if value is not None:
            settings.set_volatile(key, value)

    window = build_window(settings, window_size=args.window)

    if args.screenshot:
        import random

        import pygame

        if args.demo > 0:
            rng = random.Random(args.demo_seed)
            session = window.session
            for _ in range(args.demo):
                if session.is_over:
                    break
                move = session.game.rollout_move(session.state, rng, None, settings.weights())
                session.play(move)
            window.view.set_last_move(session.history[-1].move)

        for _ in range(12):
            window._handle_events()
            window._update(16.0)
            window._draw()
            pygame.display.flip()
        pygame.image.save(window.screen, args.screenshot)
        pygame.quit()
        print(f"截图已保存: {args.screenshot}")
        return 0

    window.run(max_frames=args.frames)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
