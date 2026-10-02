# 项目长期记忆：棋类游戏（boardgames）

可扩展的 Python 桌面棋类游戏框架。首个游戏：**步步为营（墙棋 / Quoridor）**。

## 运行方式

```bash
uv sync && uv run boardgames     # 启动
uv run pytest                    # 测试（138 项）
uv run ruff check src tests scripts
uv run python scripts/benchmark_ai.py
uv run boardgames --headless --screenshot out.png --demo 20   # 无头截图（SDL dummy）
uv run boardgames --window 1000x640                           # 强制窗口尺寸调试布局
uv run boardgames --hover wall-h                              # 截图时模拟悬停（放墙/走子预览）
```

UI 测试公用件在 `tests/ui/conftest.py`（`make_window` 夹具）与 `tests/ui/helpers.py`
（模拟鼠标/键盘），新加 UI 测试直接 `from helpers import ...` 即可。

版本管理：git（分支 `master`）。`.venv/`、`config/settings.json`、`.workbuddy/artifacts/`
已忽略；`.workbuddy/memory/` 纳入版本控制。

## 分层铁律（务必遵守）

| 层 | 允许依赖 | 禁止 |
|---|---|---|
| `core/` | 仅标准库 | import pygame、import 具体游戏 |
| `games/<key>/` | core、自己的 geometry | import ai、import ui.sidebar/window |
| `ai/` | `core.Game` 接口 | import pygame、知道 Quoridor 细节 |
| `ui/` | pygame、settings、board_view 协议 | 实现规则 |
| `controller/` | 全部（串联） | 直接绘制 |

- **状态一律不可变**：`Game.apply` 必须返回新对象。悔棋、AI 搜索、多线程读取都依赖这一点。
- **AI 线程绝不触碰 pygame**，只通过 `AIWorker.poll()` 把结果交回主循环。
- 搜索状态必须放在"每次搜索一个实例"的上下文里（`_MinimaxRun` / `_MCTSRun`），
  引擎对象本身无状态 —— 否则"取消后立刻重开"会串味。

## 新增一个棋类（扩展点）

1. `games/<key>/`：`State`(不可变 + `zobrist_hash`) / `Move`(可哈希) /
   `Game`(`initial_state`、`legal_moves`、`is_legal`、`apply`、`evaluate`、`rollout_move`)；
   用 `SearchOptions` 在搜索期裁剪组合爆炸的着法。
2. 实现 `ui/board_view.py` 的 `BoardView` 协议（`layout/draw/handle_click/handle_motion/animate/update/reset/set_last_move`）。
3. `app.py: register_builtin_views()` 里 `registry.register_view(key, factory)`；
   `core/registry.build_default_registry()` 里 `registry.register(game)`。
4. 侧栏、主题、控件、AI 调度、悔棋全部自动复用（参数加在 `settings/schema.py` 的 `SPECS`）。

## Quoridor 规则实现要点（最易错）

- 坐标 `(x=列, y=行)`，y 向下。P0 起点 `(mid, size-1)` 目标 `y==0`；P1 起点 `(mid, 0)` 目标 `y==size-1`。
- 墙用 **锚点**（`(size-1)×(size-1)`）存位掩码 `h_mask`/`v_mask`，位序 `ay*w+ax`；
  阻断的边一律**按需派生**（规模不同：`hv` 是 `w×size`，`hh` 是 `size×w`，极易 off-by-one）。
- **交叉必须用锚点判断**（同锚点反向墙＝「十」字，非法）；用边网格判断会把 L/T 形误判为非法。
- **放墙连通性必须对双方各跑一次 BFS**，只查对手会放过自杀式封路。
- 跳跃：直跳与斜跳**互斥**；直跳被墙或边界挡住才斜跳，两个斜向**各自独立**判定。

## AI 要点

- 墙分支上百，必须裁剪：只取**对手最短路径**上每条边对应的锚点，按"对手路径增量"降序取前 N 个；
  深层（`wall_depth` 之外）只展开走子。
- rollout 必须单调推进：用 `geometry.distance_field`（多源 BFS + `lru_cache`）选步，
  不要用曼哈顿距离贪心（会振荡、棋局不收敛）。已有回归测试锁住这一点。
- MCTS 子节点 `mean` 是**子节点行动方视角**，最终选步要按 `node.player == root_player` 翻符号。
- MCTS 用"越早取胜回报越高"塑形，否则胜率接近 1 时会来回拖延。
- 调参默认值（实测）：minimax depth 4 / wall_depth 2 / 1200ms；
  mcts 4000 次迭代上限 / 1200ms / max_branch 8 / rollout_cap 40 / p_wall 0.08。
  MCTS 实测 1.2s ≈ 620~720 次迭代；Minimax depth 4 ≈ 80ms。

## UI 层坑位（改侧栏 / 事件循环前必读）

- **事件处理必须判断 `event.type`**。曾出现"分组标题折叠"对**任何**事件都翻转 `expanded`，
  鼠标一划过就每帧翻一次，连标题下的下拉菜单一起疯狂抖动。折叠/按钮之类的交互
  一律限定 `MOUSEBUTTONDOWN + button == 1`。
- **`MOUSEBUTTONUP` 必须无条件派发给控件**。只在鼠标位于侧栏内时才派发，会让
  "在侧栏外松开左键"的滑块永远停在拖拽态，之后不按键鼠标一动就改数值。
  滑块自身还要在 `update()` 里用 `pygame.mouse.get_pressed()` 兜底解除。
- **`Session.is_thinking()` 必须包含 `_pending_move`**。AI 结果已返回但落子停顿（`ai_delay_ms`）
  还没过完时若返回 False，主循环每帧都会重开搜索 → "思考中"闪烁且 AI 永远不落子。
  这类 bug 只在 `ai_delay_ms > AI 思考耗时` 时暴露，测试里用大 `ai_delay_ms` 才能覆盖。
- **窗口尺寸必须裁剪到屏幕**（`ui.window.choose_window_size()`），否则小屏 / 高 DPI 下
  底部"新局/悔棋/认输"会被裁掉。侧栏宽度也随窗口自适应（`SIDEBAR_W` → `SIDEBAR_MIN_W`）。
- 中文字体按**文件路径**加载并缓存。缺字陷阱：`▾/▸` 和 `▶`（U+25B6）在微软雅黑里没有，
  别用字形画箭头 —— 用 `pygame.draw.polygon` 画。`▼/▲` 是有的。
- 面板类绘制顺序：内容 → 覆盖层（下拉弹层）最后画，并 `set_clip` 到面板矩形。

## 棋盘交互约定（Quoridor）

- **右键切换「放墙模式」**，模式本身存在 `ViewState.extra["wall_mode"]`（键 `WALL_MODE_KEY`），
  窗口负责翻转，视图只读它。**没有**"按鼠标位置自动猜走子还是放墙"那套启发式了
  —— 那套在交点附近必然抖动。
- `QuoridorView._intent()`：
  - 非放墙模式 → 只做走子（cell intent）；
  - 放墙模式 → 把鼠标分数坐标吸附到最近的**内部**网格交点
    （`line = clamp(round_half_up(f), 1, size-1)`，因此棋盘内部处处可吸附，没有"有/无提示"的跳变），
    朝向见下。
  - 只有**内部**交点能放墙（外框上没有墙槽）。
- **朝向滞回**（`_sticky_wall`）：同一交点内保持已选朝向，只有另一条线的距离明显更近
  （超过 `ORIENT_HYSTERESIS = 0.12` 格）才切换；换交点时按"离哪条线更近"重选（一样近取横墙）。
  这是"交点也能提示但不抖动"的关键。`flip_orientation()`（V 键）手动锁定朝向，
  离开当前交点后解锁。
- 放墙后 `_just_placed_wall` 抑制同一位置的重复提示（`JUST_PLACED_RADIUS = 0.75` 格）；
  放完墙由窗口自动退出放墙模式（判断依据是 `Move.is_placement`，框架级通用属性）。
- 落子/悔棋/新局后局面对象会变，`draw()` 里检测 `_intent_state is not state` 重算悬停意图。

## AI 自对弈的暂停与单步

- `GameSession.new_game()` 在 `mode == "eve"` 时 `paused = True`；
  `ai_allowed()` 决定 AI 能不能动（`not paused or stepping`），
  `start_thinking()` 用它做闸门 —— 所以窗口可以直接无条件调用。
- `request_step()` 置 `stepping = True`；`poll()` 落子后把 `stepping` 复位，`paused` 不变，
  因此单步走完仍然暂停。侧栏在 eve 模式才显示「单步」「暂停」两个按钮。

## 侧栏按模式精简 + 数值输入

- `ParamSpec` 有 `needs_ai` / `needs_engine` 两个可见性条件；`Sidebar` 从
  `status.player_types` 解析"实际参战引擎集合"，据此过滤分组与单个参数。
  新增参数时记得标好归属，否则会在不该出现的模式下露出来。
- **双方信息固定在头部**（`PLAYERS_Y`），不参与滚动 —— 侧栏滚动区只放参数。
  `HEADER_H = 178`，改头部高度时记得同步 `theme.MIN_WINDOW_H` 的可用性。
- **数值参数可点击输入**：`Slider.value_box` 是右侧的数值框，点它进入编辑态；
  `Sidebar.handle_key()` 在编辑时**接管所有键盘事件**并返回 True，
  否则 Esc / N / U 会误触发退出、新局、悔棋。
  `Sidebar._editing` 保证同时只有一个在编辑，点其他地方 = 确认。


## 用户偏好（本次交互确认）

- UI：**Pygame 桌面窗口**，深色现代主题，中文界面。
- 必须同时有：双人同屏、人机、AI 自对弈；AI 参数在**侧栏实时可调**。
- 棋盘尺寸/墙数**可配置**（默认 9×9 + 10 墙）。
- 墙规则取**严格标准**（禁重叠 + 禁交叉）；先手可选（默认玩家 1）。
- 本期只做步步为营，但架构要留好扩展点。
