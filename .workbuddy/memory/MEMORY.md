# 项目长期记忆：棋类游戏（boardgames）

可扩展的 Python 桌面棋类游戏框架。已内置两个游戏：**步步为营（墙棋 / Quoridor）**
与**重力四子棋（Connect Four）**。

## 运行方式

```bash
uv sync && uv run boardgames     # 启动（先进大厅）
uv run pytest                    # 测试（233 项）
uv run ruff check src tests scripts
uv run python scripts/benchmark_ai.py
uv run boardgames --game connect4 --cols 8 --rows 7    # 直接进四子棋
uv run boardgames --scene match                         # 跳过大厅
uv run boardgames --headless --screenshot out.png --demo 20 --scene match   # 无头截图
uv run boardgames --headless --screenshot lobby.png --scene lobby          # 拍大厅
uv run boardgames --window 1000x640                     # 强制窗口尺寸调试布局
uv run boardgames --hover wall-h --scene match          # 截图时模拟悬停（按棋类分派）
```

UI 测试公用件在 `tests/ui/conftest.py`（`make_window` 夹具，支持 `game_key=` /
`start_scene=` 关键字，会从 overrides 里抠出来传给 `GameWindow`）与 `tests/ui/helpers.py`
（模拟鼠标/键盘），新加 UI 测试直接 `from helpers import ...` 即可。
⚠️ 造局面优先用 `tests/games/connect4/conftest.py` 的 `make_at(cols, rows, {(col,row):值})`
——按坐标写、其余自动填充，能保证重力；手写棋盘图字符串极易抄错。

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

1. `games/<key>/`：`State`(不可变 + `zobrist_hash`) / `Move`(`@dataclass(frozen=True, slots=True)`) /
   `Game`(`initial_state`、`legal_moves`、`is_legal`、`apply`、`evaluate`、`rollout_move`)；
   用 `SearchOptions` 在搜索期裁剪组合爆炸的着法。
2. 实现 `ui/board_view.py` 的 `BoardView` 协议（`layout/draw/handle_click/handle_motion/animate/update/is_animating/reset/set_last_move`）。
   可选实现 `hover_hint()` / `hud_hint()` 拿专属提示文案（窗口用 `hasattr` 检测）。
   **视图必须保留 `origin` 与 `cell` 两个属性名** —— `tests/ui/helpers.py:pos_for()` 依赖。
3. `app.py: register_builtin_views()` 里 `registry.register_view(key, factory)`；
   `core/registry.build_default_registry()` 里 `registry.register(game)`。
4. 侧栏参数加在 `settings/schema.py` 的 `SPECS`，**必须打 `games=(key,)` 标**。
5. 大厅卡片**零改动** —— 卡片数据来自 `Game` 的 `tagline` / `summary` / `rules` / `icon` ClassVar。

侧栏、主题、控件、AI 调度、悔棋、后台搜索线程、大厅全部自动复用。

## 构造参数注入：Game.settings_map

`GameSession._build_game` 早期版本给构造器硬传 `size=/walls=/first_player=` 并
`except TypeError` 兜底 —— **实测会静默丢弃 `first_player=p2`，且回退到注册表的共享单例**
（跨对局状态污染）。现在改为各 `Game` 自己声明：

```python
settings_map: ClassVar[Mapping[str, str]] = {}   # settings 键 -> 构造参数名
```

必须是纯 `ClassVar`（core 不能 import settings —— `settings.store` 已依赖 `ai.engine`，
反向 import 会成环）。

## Connect Four 规则实现要点

- 坐标 `(col, row)`，**row 0 是最底行**。棋盘存一维 `cells`（下标 `row*cols+col`，
  0 空 / 1 玩家1 / 2 玩家2）+ **冗余** `heights`（投子目标行 = `heights[col]`，
  威胁检测要遍历所有列的下一格，从 `cells` 推导是 O(cols×rows)，rollout 里被调用上百万次）。
- **`winner_player` 存玩家索引（0/1）而不是棋子值（1/2）**。引擎会拿 `state.winner()`
  直接和玩家索引比较，用棋子值会让符号整个反过来 —— 实测 minimax 深度 1~6 全部找不到
  "三连直接赢"这种必胜手。
- **字段绝不能叫 `winner`**：`State.winner()` 是 ABC 抽象方法，同名字段会遮蔽它，
  `minimax` 里 `state.winner()` 会拿到非可调用对象。
- `scan_win` **落点两侧的连子数必须相加**再比较 `>= 4`。写成「正反两方向各自独立计数再判断」
  会让"落点补上横四/斜四中间那一子"（`X.XX` → 投中间变 `XXXX`）永远判不出胜负。
- `is_terminal()` 用 `all(h >= rows)` 而非 `ply >= cols*rows` —— 手搭测试局面时
  `ply` 可能与棋盘不同步。
- `zobrist_hash` 排除 `heights` / `ply` / `winner_player`（都能从 `cells` 推出）。
- **收敛性天然成立**：每步必然 `ply += 1` 且棋盘不可逆填满，任何合法序列都在
  ≤ `cols*rows` 步内终止 —— 不像墙棋棋子能来回走，振荡在数学上不可能发生。
- **`legal_moves` 必须完全忽略 `max_branch` 与 `include_walls`**。分支因子本来就小；
  而 minimax 的 `include_walls = ply < wall_depth` 是为墙棋的墙分支设计的，
  当成"裁剪着法"会让深度 ≥2 的节点只剩 ≤1 个着法，棋力直接崩却查不出原因。
- **不能有 tempo（节奏）项**：墙棋里"轮到谁走"有先后优势，四子棋没有（先手优势已体现在
  先落子的棋子上）。加这一项会破坏 `evaluate(s,0) == -evaluate(s,1)`，minimax 在双方都
  不占便宜的局面里乱选。同理攻/防威胁必须**共用一个权重**（`w_threat`）。
- 评估分**对称性有回归测试**锁住（`evaluate(s,0) == -evaluate(s,1)`）。
- **`count_pieces()` 别用"总格数 − 已落子数"算对手** —— 那是**空格数**，空盘会报"对手已落 42 子"。
  正确写法 `heights_total() - p0`。
- **调色板索引一律用玩家号 0/1**（`theme.PLAYER_COLORS` 只有 2 项）。写成 `棋子值 = 玩家号 + 1`
  会让**玩家 2 悬停**（`_draw_ghost`）和**玩家 2 赢棋**（`_draw_win_line`）直接 IndexError。

## Connect Four 视图（渲染层最易错）

- **局面行号与屏幕行号是反的**：`row == 0` 是最底行，屏幕 y 向下增大。
  翻转只在 `Connect4View.screen_row(row) = rows - 1 - row` 一处做，`cell_center` 内部用它。
  **两处各翻一次 = 没翻**（症状：整盘棋子堆在棋盘顶部）。
- **`Game` 侧只提供"谁能赢"的语义，视图不实现规则**；但渲染类 bug（上下颠倒、差半格）
  用断言数据结构的测试**永远抓不到** —— 必须"画一帧再取像素"：
  `surface.get_at(view.cell_center(col, 0))[:3] == theme.PLAYER_COLORS[0]`。
- 落子预览（ghost）必须与圆窝**同心同径**：中心就是 `cell_center(col, heights[col])`，
  半径就是 `socket_radius`。给它加"浮在上方"的纵向偏移 = 看着没对准。
- **正在下落的那一枚要最后画**：它要穿过已有棋子掉到槽位，先画会被沿途棋子盖住。
- 高亮跟**最后一手**（`_last_move`）走，不给当前行动方的所有棋子加光环 —— 颜色已经说明归属。

## 场景架构（大厅 ↔ 对局）

- `ui/scene.py` 的 `Scene` Protocol：`on_enter` / `on_exit` / `layout` / `handle_event` / `update` / `draw`。
- `GameWindow` **只**是窗口宿主（screen / clock / QUIT / VIDEORESIZE / 设置落盘），其余全下发 scene。
- `MatchScene` 持 session / view / sidebar / view_state / toast；`LobbyScene` 持卡片。
- **转发 property 是保住测试的关键**：`tests/ui/*.py` 有 205 处 `window.xxx` 访问，
  Python 属性解析不穿透到 scene，所以 `GameWindow` 暴露 `session` / `view` / `sidebar` /
  `view_state` / `board_area` / `sidebar_rect` / `toast` 与 `_update` / `_draw` /
  `_on_setting` / `_on_action` / `_handle_events` 全部转发给 `match`。
- **`GameWindow(start_scene=...)` 默认必须是 `"match"`**（不是 lobby），这样既有
  `make_window()` 夹具零改动。生产入口 `app.main` 显式传 `start_scene="lobby"`。
  默认反直觉，已在 docstring 注明原因。
- **scene 必须每帧从 `window.screen` 读 surface**，绝不能缓存引用 ——
  `test_layout_fits_a_small_window` 会直接 `set_mode` 换掉窗口表面。
- 回大厅**必须先 `session.cancel_thinking()`**（`MatchScene.on_exit` 做的），
  否则后台 AI 线程继续跑并持有旧局面引用。
- `Esc` 语义是**三级**：退放墙模式 → 回大厅 → （大厅里）退出程序。
- `PLACEMENT_MODE_KEY` 定义在 `ui/board_view.py`，`quoridor/view.py` 保留
  `WALL_MODE_KEY = PLACEMENT_MODE_KEY` 同值别名 → 8 个引用它的测试零改动。

## 弹跳下落动画（`ui/animation.py: BounceTween`）

物理积分而非补间曲线。三条都是必需项，不是优化：

- **固定子步积分 1/240 秒**。朴素半隐式欧拉在 `dt=33ms`（掉帧）时反弹 440 次、
  持续 4 秒、**锁死输入**。`window.run()` 里 `dt_ms = min(dt_ms, 100)` 的上限意味着
  切后台回来必踩。
- **重力按落差归一化**（`gravity ∝ drop_px`），否则底部落子 458ms、顶部 1458ms。
  用「反解重力让实际时长逼近 duration_s」实现，缩放钳在 `[0.35, 2.5]`。
- **超时兜底必须在子步循环之外**：若棋子一直悬在半空、始终碰不到 `drop_px`，
  落在触底分支里的超时判定永远不触发，会永远播下去并锁死输入。
- `done` 不能只看 `_v == 0`（初始速度就是 0），要用独立的 `_landed` 标志。
- 动画**不排队**：新动画直接顶掉旧的。AI 双方连续落子时排队会累积延迟。
- 只给**最后一手**的那枚棋子加偏移（`DropMove` 存了 `row` 和 `player` 供认领）。
- **`offset()` 是 `_y - drop_px`，不是 `-_y`**。`_y` 存"**已经落下的距离**"（0 → `drop_px`），
  写成 `-_y` 就等于"从槽位里往上飞出去、最后悬在棋盘上空"，也就是"重力方向反了"。
  退化分支（`duration<=0` / `drop_px<=0`）要把 `_y` 置成 `drop_px` 才等于"已静止在槽位"。
- `duration_ms == 0` → 不播放（沿用 QuoridorView 的约定）。
- 四子棋的落差由 `Connect4View.drop_px_for(row)` 给：**所有棋子从棋盘上沿之上
  `DROP_ENTRY_CELLS` 格进场，落点越低掉得越远**（真棋具就是从顶口投子）。
  别用固定落差 —— 翻转坐标后固定落差会让棋子"在棋盘中间凭空出现"。

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
- **`ROLLOUT_VALUE_SCALE = 600` 是给墙棋调的**（墙棋 `w_path=100`/步，评估分轻松上百）。
  四子棋评估分小得多，但**实测没问题**（2026-10-03：minimax depth6 vs mcts 4000iter
  各 8 局 4:4，0 平；两者都能抓住必胜与必防）。四子棋的 rollout 策略本身够强
  （贪心 + 威胁优先 + 中心加权随机），回报仍有区分度。**不要动这个常量**。

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

## 侧栏按模式 + 按游戏精简 + 数值输入

- `ParamSpec` 有 `needs_ai` / `needs_engine`（按引擎过滤）+ **`games`（按棋类过滤）**
  三个可见性条件；`Sidebar` 从 `status.player_types` 解析"实际参战引擎集合"，
  从构造参数 `game_key` 解析当前棋类，据此过滤分组与单个参数。
  **新增参数时务必标好 `games=`，否则会在别的棋类侧栏里露出来。**
- **双方信息固定在头部**（`PLAYERS_Y`），不参与滚动 —— 侧栏滚动区只放参数。
  `HEADER_H = 178`，改头部高度时记得同步 `theme.MIN_WINDOW_H` 的可用性。
- **玩家行详情泛化**：`Status.player_details` 只放**数值部分**（"墙 10" / "已落 12 子"），
  类型标签由侧栏自己拼上去；留空回退到 `walls_left`。
- **侧栏标题/副标题**从 `game.display_name` / `game.tagline` 取（`Sidebar.set_game()`）。
- **数值参数可点击输入**：`Slider.value_box` 是右侧的数值框，点它进入编辑态；
  `Sidebar.handle_key()` 在编辑时**接管所有键盘事件**并返回 True，
  否则 Esc / N / U 会误触发退出、新局、悔棋。
  `Sidebar._editing` 保证同时只有一个在编辑，点其他地方 = 确认。
- 底栏 6 个按钮（最小侧栏 316px 下每格 40px，中文两字 28px 放得下）；
  `Button.draw` 在按钮宽度不足时会降一档字号。`_footer_enabled` 按 `button.key` 分派
  （label 会被改文案，key 才稳定）。

## 用户偏好（本次交互确认）

- UI：**Pygame 桌面窗口**，深色现代主题，中文界面。
- 必须同时有：双人同屏、人机、AI 自对弈；AI 参数在**侧栏实时可调**。
- 棋盘尺寸/墙数**可配置**（默认 9×9 + 10 墙）。
- 墙规则取**严格标准**（禁重叠 + 禁交叉）；先手可选（默认玩家 1）。
- **启动即游戏选择大厅**（卡片网格 + 简介），侧栏底栏有「大厅」按钮可返回。
- 四子棋：列 / 行**可调**（5-12 / 4-10），**连线数固定 4**。
- AI **复用现有引擎**（minimax + mcts）+ 棋类专属评估函数，不另建位运算引擎。
- 动画要**真的物理**（重力弹跳），不要 ease-out 补间凑。
