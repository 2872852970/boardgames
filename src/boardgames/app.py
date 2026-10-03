"""应用入口：组装注册表、设置与窗口。

框架不在这里写任何游戏规则 —— 新增棋类时只需：

1. 在 ``games/`` 下实现 ``Game`` / ``State`` / ``Move`` / ``BoardView``；
2. 在 :func:`build_default_registry`（``core/registry.py``）里注册游戏；
3. 在 :func:`register_builtin_views` 里注册它的视图工厂；
4. 若它有专属的侧栏参数，在 ``settings/schema.py`` 的 ``ParamSpec`` 上打 ``games=`` 标。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

from boardgames.core.registry import GameRegistry, build_default_registry
from boardgames.settings import Settings

#: 各棋类"截图时模拟悬停"的实现。注册视图时一起填好（见 :func:`register_builtin_views`）。
_HOVER_SIMS: dict[str, Callable[[object, str], None]] = {}


def register_builtin_views(registry: GameRegistry) -> None:
    """把各棋类的棋盘视图挂到注册表上（UI 相关的 import 集中在这里）。"""
    from boardgames.games.connect4.view import make_view as connect4_view
    from boardgames.games.quoridor.view import make_view

    registry.register_view("quoridor", make_view)
    registry.register_view("connect4", connect4_view)
    _HOVER_SIMS["quoridor"] = _hover_quoridor
    _HOVER_SIMS["connect4"] = _hover_connect4


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
    registry = build_registry()
    parser = argparse.ArgumentParser(
        prog="boardgames",
        description="棋类游戏 · " + " / ".join(g.display_name for g in registry.all_games()),
    )
    parser.add_argument("--game", choices=sorted(registry.keys()), default="quoridor",
                        help="选择棋类（默认 quoridor）")
    parser.add_argument("--scene", choices=("lobby", "match"), default="lobby",
                        help="启动场景：lobby=游戏选择大厅（默认），match=直接进对局")
    parser.add_argument("--headless", action="store_true", help="不打开窗口（用 dummy 视频驱动）")
    parser.add_argument("--frames", type=int, default=None, help="跑固定帧数后自动退出（自检用）")
    parser.add_argument("--mode", choices=("pvp", "pve", "eve"), default=None)
    parser.add_argument("--p1", choices=("human", "minimax", "mcts", "random"), default=None)
    parser.add_argument("--p2", choices=("human", "minimax", "mcts", "random"), default=None)
    parser.add_argument("--size", type=int, default=None, help="步步为营：棋盘尺寸")
    parser.add_argument("--walls", type=int, default=None, help="步步为营：每人墙数")
    parser.add_argument("--cols", type=int, default=None, help="重力四子棋：列数")
    parser.add_argument("--rows", type=int, default=None, help="重力四子棋：行数")
    parser.add_argument("--screenshot", default=None, help="渲染若干帧后截图到指定路径")
    parser.add_argument("--demo", type=int, default=0, help="截图前先按策略走 N 步，方便看中局画面")
    parser.add_argument("--demo-seed", type=int, default=7, help="demo 走子的随机种子")
    parser.add_argument(
        "--window", type=_parse_size, default=None, help="强制窗口尺寸，如 1000x640（用于验证布局）"
    )
    parser.add_argument(
        "--hover",
        choices=("none", "wall-h", "wall-v", "corner", "cell", "drop", "drop-mid"),
        default="none",
        help="截图时模拟鼠标悬停，用来拍下预览 / 高亮（按棋类分派）",
    )
    parser.add_argument("--card", default=None,
                        help="大厅截图时高亮这张卡片（游戏 key）")
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
        "connect4_cols": args.cols,
        "connect4_rows": args.rows,
    }
    for key, value in overrides.items():
        if value is not None:
            settings.set_volatile(key, value)

    # 产品入口默认进大厅（测试夹具才用 start_scene="match" 的默认值）
    window = build_window(
        settings, window_size=args.window,
        game_key=args.game, start_scene=args.scene,
    )

    if args.screenshot:
        import pygame

        if args.card and window.lobby is not None:
            for i, card in enumerate(window.lobby._cards):
                if card.game.key == args.card:
                    window.lobby._focus = i
                    window.lobby._hover = i
                    break

        # --demo 只对局场景有意义（大厅里没有 session 可走）
        if args.demo > 0 and args.scene == "match":
            import random

            rng = random.Random(args.demo_seed)
            session = window.session
            for _ in range(args.demo):
                if session.is_over:
                    break
                move = session.game.rollout_move(session.state, rng, None, settings.weights())
                session.play(move)
            window.view.set_last_move(session.history[-1].move)

        if args.hover != "none" and args.scene == "match":
            sim = _HOVER_SIMS.get(window.game_key)
            if sim is not None:
                sim(window, args.hover)

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


# --------------------------------------------------------------------------- #
# 截图辅助：把鼠标"放"到某个位置，好拍下悬停预览
# --------------------------------------------------------------------------- #


def _hover_quoridor(window, mode: str) -> None:
    from boardgames.ui.board_view import PLACEMENT_MODE_KEY

    session = window.session
    view = window.view
    state = session.state
    if mode in ("cell", "drop", "drop-mid"):
        window.view_state.extra[PLACEMENT_MODE_KEY] = False
        moves = session.game.pawn_moves_for(state, state.current_player)
        if not moves:
            return
        pos = view.cell_center(*moves[0].dst)
    else:
        window.view_state.extra[PLACEMENT_MODE_KEY] = True
        orient = "v" if mode == "wall-v" else "h"
        walls = [w for w in session.game.all_legal_walls(state, state.current_player)
                 if w.orient == orient]
        if not walls:
            return
        pos = view.anchor_center(walls[len(walls) // 2].wall)
        if mode != "corner":
            # 交点上也能提示；这里沿这条边挪开一点，拍"贴着边放墙"的常规用法
            offset = max(1, int(view.cell * 0.4))
            pos = (pos[0] + offset, pos[1]) if orient == "h" else (pos[0], pos[1] + offset)
    window.view_state.mouse = pos
    view.handle_motion(pos, session.game, state, window.view_state)


def _hover_connect4(window, mode: str) -> None:
    """四子棋：悬停某列会显示"落子预览"幽灵棋子。"""
    session = window.session
    view = window.view
    state = session.state
    open_cols = [c for c in range(state.cols) if state.heights[c] < state.rows]
    if not open_cols:
        return
    if mode == "drop":
        # 中间那列（视觉上最有代表性）
        col = open_cols[len(open_cols) // 2]
    else:  # drop-mid：靠近中间偏右
        col = open_cols[min(len(open_cols) - 1, len(open_cols) // 2 + 1)]
    pos = view.cell_center(col, state.heights[col])
    window.view_state.mouse = pos
    view.handle_motion(pos, session.game, state, window.view_state)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
