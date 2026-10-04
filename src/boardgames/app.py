"""应用入口：组装注册表、设置与窗口。

框架不在这里写任何游戏规则 —— 新增棋类时只需：

1. 在 ``games/`` 下实现 ``Game`` / ``State`` / ``Move`` / ``BoardView``；
2. 在 :func:`build_default_registry`（``core/registry.py``）里注册游戏；
3. 在 :func:`register_builtin_views` 里注册它的视图工厂；
4. 若它有专属的侧栏参数，在 ``settings/schema.py`` 的 ``ParamSpec`` 上打 ``games=`` 标。
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable

from boardgames.core.registry import GameRegistry, build_default_registry
from boardgames.settings import Settings

#: 各棋类"截图时模拟悬停"的实现。注册视图时一起填好（见 :func:`register_builtin_views`）。
_HOVER_SIMS: dict[str, Callable[[object, str], None]] = {}


def register_builtin_views(registry: GameRegistry) -> None:
    """把各棋类的棋盘视图挂到注册表上（UI 相关的 import 集中在这里）。"""
    from boardgames.games.abalone.view import make_view as abalone_view
    from boardgames.games.connect4.view import make_view as connect4_view
    from boardgames.games.dotsboxes.view import make_view as dotsboxes_view
    from boardgames.games.hive.view import make_view as hive_view
    from boardgames.games.mancala.view import make_view as mancala_view
    from boardgames.games.quoridor.view import make_view

    registry.register_view("quoridor", make_view)
    registry.register_view("connect4", connect4_view)
    registry.register_view("abalone", abalone_view)
    registry.register_view("hive", hive_view)
    registry.register_view("dotsboxes", dotsboxes_view)
    registry.register_view("mancala", mancala_view)
    _HOVER_SIMS["quoridor"] = _hover_quoridor
    _HOVER_SIMS["connect4"] = _hover_connect4
    _HOVER_SIMS["abalone"] = _hover_abalone
    _HOVER_SIMS["hive"] = _hover_hive
    _HOVER_SIMS["dotsboxes"] = _hover_dotsboxes
    _HOVER_SIMS["mancala"] = _hover_mancala


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


def _run_until_over(window, timeout_s: float = 180.0) -> None:
    """跑主循环直到分出胜负 —— 无头自对弈的"完整跑完"入口。

    三件事都不能少：

    * **解除暂停**：AI 自对弈默认是暂停的（方便一着一看），跑到终局得先放开；
    * **关掉动画、也不锁 60 帧**：没人看画面，动画只是白白拖长一盘棋的墙钟时间；
    * **留真实时间上限**：局面卡住时不能死等，超时也要正常收工并说明；
    * 结束时打印终局文案，让"有没有真的分出胜负"在日志里看得见。
    """
    import pygame

    session = window.session
    session.paused = False
    for key in ("anim_ms", "c4_anim_ms", "abalone_anim_ms", "hive_anim_ms", "mancala_anim_ms"):
        window.settings.set_volatile(key, 0)

    started = time.monotonic()
    deadline = started + timeout_s
    last_report = started
    print(
        "自对弈参数："
        + " ".join(
            f"{k}={window.settings.get(k)}"
            for k in ("p1_type", "p2_type", "minimax_depth", "minimax_time_ms",
                      "mcts_time_ms", "ai_delay_ms")
        )
    )
    while window.running and not session.is_over and time.monotonic() < deadline:
        window._handle_events()
        window.clock.tick(0)  # 不限帧：能跑多快跑多快，别按 60fps 空转
        window._update(16.0)
        window._draw()
        pygame.display.flip()
        # 无头跑几分钟一句话都不说很难受，也不知道是"在想"还是"卡住了"
        now = time.monotonic()
        if now - last_report >= 10:
            last_report = now
            print(
                f"  [{now - started:4.0f}s] 已走 {len(session.history) - 1:>3} 手 · "
                f"{'AI 思考中' if session.is_thinking() else '等待中'}"
            )
    if session.is_over:
        print("对局结束：", session.result_text())
    else:
        print(f"到达 {timeout_s:.0f}s 上限仍未分胜负，可以用 --timeout 调大")
    window._flush_settings()
    pygame.quit()


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
    # 无边框默认**跟着设置走**（界面分组里那个开关，默认开），命令行可以强制覆盖
    parser.add_argument(
        "--frameless", "--headless", dest="frameless", action="store_true", default=None,
        help="无边框窗口：不要系统标题栏，改由程序自己画一条（含关闭 / 全屏 / 拖动）",
    )
    parser.add_argument(
        "--windowed", dest="frameless", action="store_false",
        help="用回系统的标题栏（覆盖设置里的「无边框窗口」）",
    )
    parser.add_argument(
        "--offscreen", action="store_true",
        help="完全不显示窗口（SDL dummy 驱动），给 CI / 跑批 / 截图脚本用",
    )
    parser.add_argument("--frames", type=int, default=None, help="跑固定帧数后自动退出（自检用）")
    parser.add_argument(
        "--until-over", action="store_true",
        help="一直跑到分出胜负再退出（看完整一局 / 无头自对弈用；配合 --timeout）",
    )
    parser.add_argument(
        "--timeout", type=float, default=600.0,
        help="配合 --until-over 的真实时间上限（秒），防止卡在某个局面里不出来",
    )
    parser.add_argument(
        "--fast-ai", action="store_true",
        help="把 AI 调成演示速度（每步约 0.3s，不写回配置文件），配合 --until-over 用",
    )
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
        choices=("none", "wall-h", "wall-v", "corner", "cell", "drop", "drop-mid",
                 "aba-select", "hive-place", "hive-select", "dots-edge", "mancala-pit"),
        default="none",
        help="截图时模拟鼠标悬停，用来拍下预览 / 高亮（按棋类分派）",
    )
    parser.add_argument("--card", default=None,
                        help="大厅截图时高亮这张卡片（游戏 key）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
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

    if args.fast_ai:
        # 演示速度：不写回配置文件（volatile），只影响这次运行。
        # 配置文件里可能存着"调参用"的激进值（例如 Minimax 15s 时限），
        # 那样一局自对弈要十几分钟 —— 想"看完一整局"时用这个开关。
        for key, value in (
            ("minimax_time_ms", 300), ("mcts_time_ms", 300), ("mcts_iterations", 2000),
        ):
            settings.set_volatile(key, value)

    # --until-over 得在**对局**场景里才有意义：大厅场景的 update 不会推进棋局
    if args.until_over and args.scene != "match":
        args.scene = "match"

    # 产品入口默认进大厅（测试夹具才用 start_scene="match" 的默认值）
    frameless = (
        bool(settings.get("frameless_window")) if args.frameless is None else args.frameless
    )
    window = build_window(
        settings, window_size=args.window,
        game_key=args.game, start_scene=args.scene,
        frameless=frameless, offscreen=args.offscreen,
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

        # 先跑两帧让布局与摄像机就位 —— 悬停模拟要把**格坐标换算成屏幕坐标**，
        # 而昆虫棋的换算是靠摄像机的（自适应缩放只在 update 里发生）。
        for _ in range(2):
            window._handle_events()
            window._update(16.0)
            window._draw()
            pygame.display.flip()

        if args.hover != "none" and args.scene == "match":
            sim = _HOVER_SIMS.get(window.game_key)
            if sim is not None:
                sim(window, args.hover)

        for _ in range(10):
            window._handle_events()
            window._update(16.0)
            window._draw()
            pygame.display.flip()
        pygame.image.save(window.screen, args.screenshot)
        pygame.quit()
        print(f"截图已保存: {args.screenshot}")
        return 0

    if args.until_over:
        _run_until_over(window, args.timeout)
        return 0

    if window.offscreen and args.frames is None:
        print(
            "正在离屏运行（没有窗口画面）。用 --frames N 跑固定帧数，"
            "或 --until-over 跑完整一局（例如：\n"
            f"  uv run boardgames --game {args.game} --scene match --mode eve --offscreen --until-over"
        )
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


def _hover_hive(window, mode: str) -> None:
    """昆虫棋：拍下"选手牌 → 亮出落点"或"选棋子 → 亮出落点"的画面。"""
    session = window.session
    view = window.view
    state = session.state
    if mode == "hive-place":
        # 手牌条的位置是 draw() 里才排的，截图时可能还没画过一帧 —— 先排一次
        view._layout_cards(state, state.current)
        # 挑一张**还有货**的卡：第一张常常是"蜂后 0"（早落场了），点了没有落点
        kind = next(
            (k for k in view._cards if state.hand_left(state.current, k) > 0), None
        )
        if kind is None:
            return
        pos = view._cards[kind].center
        view.handle_click(pos, session.game, state, window.view_state)
        view.handle_motion(pos, session.game, state, window.view_state)
        return
    moves = session.game.legal_moves(state)
    if not moves:
        return
    # 优先选一枚己方已入场的棋（没有就只能放置）
    best = next(
        (m for m in moves if getattr(m, "src", None) is not None and m.src != getattr(m, "dest", None)),
        None,
    )
    if best is None:
        return
    pos = view.cell_center(best.src)
    view.handle_click(pos, session.game, state, window.view_state)
    view.handle_motion(pos, session.game, state, window.view_state)


def _hover_abalone(window, mode: str) -> None:
    """大力士棋：选中一枚己方棋子，把"选中 + 目标格箭头"拍下来。"""
    session = window.session
    view = window.view
    state = session.state
    moves = session.game.legal_moves(state)
    if not moves:
        return
    # 优先挑一手带推挤的，画面信息量最大
    best = next((m for m in moves if m.ejected is not None or m.pushed), moves[0])
    pos = view.cell_center(best.cells[0])
    window.view_state.mouse = pos
    view.handle_click(pos, session.game, state, window.view_state)
    view.handle_motion(pos, session.game, state, window.view_state)


def _hover_dotsboxes(window, mode: str) -> None:
    """点格棋：把鼠标放到一条还没画的边上，拍下悬停预览。"""
    from boardgames.games.dotsboxes import heuristic as heu

    session = window.session
    view = window.view
    state = session.state
    # 找一条能封口的边（画面最有代表性），没有就随便挑一条空边
    closing = None
    for i, drawn in enumerate(state.h_edges):
        if not drawn:
            row, col = divmod(i, state.size - 1)
            if heu.boxes_closed_by_move(state, 0, row, col):
                closing = (0, row, col)
                break
    if closing is None:
        for i, drawn in enumerate(state.h_edges):
            if not drawn:
                row, col = divmod(i, state.size - 1)
                closing = (0, row, col)
                break
    if closing is None:
        return
    orient, row, col = closing
    a, b = view._edge_segment(orient, row, col)
    pos = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
    window.view_state.mouse = pos
    view.handle_motion(pos, session.game, state, window.view_state)


def _hover_mancala(window, mode: str) -> None:
    """播棋：把鼠标放到己方第一个非空坑上，拍下播种预览。"""
    session = window.session
    view = window.view
    state = session.state
    moves = session.game.legal_moves(state)
    if not moves:
        return
    pit = moves[0].pit
    col = view._pit_to_col(state.current, pit)
    pos = view._pit_center(state.current, col)
    window.view_state.mouse = pos
    view.handle_motion(pos, session.game, state, window.view_state)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
