# 项目总结 · 架构总览

> 这份文档回答两个问题：**这个项目由哪些部分构成**、**当我准备接一个新棋类时，哪些东西是我可以白拿的**。
> 具体怎么动手写在 [`ADDING_A_GAME.md`](./ADDING_A_GAME.md)，踩过的坑集中在本文末尾与那份文档的「坑清单」。

---

## 1. 项目定位

**用 Python + Pygame 从零写棋类游戏，顺便把「怎么做」讲清楚。**

- **依赖只有一个 `pygame-ce`**（外加 dev 依赖 `pytest` / `ruff`）。规则几何、AI 搜索、界面控件、
  动画物理、摄像机全部手写，不引第三方游戏框架 / GUI 库 / 数学库。原因是这个项目的一半价值在
  **可读的、能学习的实现**：六边形坐标怎么换算、Alpha-Beta 怎么剪枝、无边界棋盘怎么写漫游，
  自己写一遍比调库有意思得多。
- **目标是「加第五个棋类成本极低」**：规则、AI、界面三层解耦，新棋类只写**规则引擎 + 一块棋盘视图**，
  侧栏、主题、控件、AI 调度（含后台线程）、悔棋、游戏大厅、规则浮层、设置持久化**全部自动复用**。
- 当前内置四个棋类，它们分别代表四种典型的棋盘/交互形态，也是框架的四个"验收样本"：

| 棋类 | key | 形态特征 | 它对框架提出的新要求 |
|---|---|---|---|
| 步步为营（墙棋） | `quoridor` | 方格 + **两种着法类型**（走子 / 放墙） | 组合爆炸型分支需要裁剪；放置模式；墙的合法性 |
| 重力四子棋 | `connect4` | 方格 + 重力 | 落子**动画物理**；小分支因子不做裁剪 |
| 大力士棋 | `abalone` | **六边形**棋盘 + 推挤 | `max_branch` 真正派上用场；"以多推少"的复合着法 |
| 昆虫棋 | `hive` | **无边界** + **叠层** + 手牌 | 摄像机；局面平移归一化哈希；显式 pass 着法 |

---

## 2. 目录地图

```
src/boardgames/
├── core/            (312 行) 游戏无关抽象 —— 依赖只有标准库
│   ├── state.py        State  ABC：current_player / is_terminal / winner / zobrist_hash
│   ├── move.py         Move   ABC：player / is_placement
│   ├── game.py         Game   ABC（唯一扩展契约）+ SearchOptions（搜索期裁剪选项）
│   ├── player.py       PlayerMeta：玩家展示信息
│   ├── result.py       GameResult：终局结果的文案与类型
│   └── registry.py     GameRegistry：key -> (Game, view_factory)
│
├── games/<key>/     规则 + 视图，一个棋类一个包
│   ├── state.py        不可变局面（+ 增量维护的哈希）
│   ├── move.py         frozen dataclass 着法
│   ├── rules.py        Game 子类：六个必需方法 + 元数据 ClassVar
│   ├── heuristic.py    evaluate 的实现与权重表
│   ├── geometry.py     棋盘几何（纯数学，不碰 pygame）— 按需
│   ├── layouts.py      起始布局（纯数据）— 按需
│   └── view.py         棋盘视图（BoardView 协议）
│
├── ai/              (855 行) 搜索 —— 只认 core.Game 接口
│   ├── engine.py       AIEngine ABC / SearchContext（取消+时限）/ SearchResult / SearchStats
│   ├── minimax.py      负极大值 + Alpha-Beta + 迭代加深 + 置换表
│   ├── mcts.py         UCB1 + 惰性展开 + 启发式 rollout
│   ├── tt.py           Zobrist 置换表
│   ├── random_ai.py    随机引擎（兜底 / 基准）
│   ├── worker.py       AIWorker：后台线程 + poll() 交回主循环
│   └── __init__.py     引擎注册表（新增算法加一行）
│
├── controller/
│   └── session.py     (324 行) GameSession：模式、悔棋、AI 编排、暂停/单步
│
├── settings/
│   ├── schema.py      (305 行) ParamSpec 参数描述表 + WEIGHT_KEYS
│   └── store.py       读写 config/settings.json，按 schema 校验
│
└── ui/              (3844 行) 界面 —— 不实现任何规则
    ├── scene.py          Scene Protocol（on_enter/on_exit/layout/handle_event/update/draw）
    ├── window.py         GameWindow：窗口宿主 + 主循环 + 场景切换 + 尺寸裁剪
    ├── lobby.py          游戏选择大厅（卡片由 Game 元数据自动生成）
    ├── match_scene.py    对局场景：棋盘 + 侧栏 + AI 调度 + 结算浮层 + 提示胶囊
    ├── sidebar.py        侧栏：分组、滑块/下拉/开关、数值直接输入
    ├── rules_panel.py    规则说明浮层（大厅与对局共用）
    ├── camera.py         摄像机 + CameraController（平移/缩放/自动适配/点击与拖拽裁决）
    ├── animation.py      BounceTween：固定子步积分的弹跳下落
    ├── chrome.py         无边框窗口的自绘标题栏
    ├── theme.py          配色（玩家色、棋盘色、状态色）
    ├── fonts.py          中文字体加载与缓存
    ├── render.py         圆角矩形、阴影、文字等绘制原语
    ├── board_view.py     BoardView Protocol + ViewState（视图状态）
    └── widgets/          控件：base / controls（按钮、滑块、下拉、开关）
```

测试按被测层次分目录：`tests/core`、`tests/games/<key>`、`tests/ai`、`tests/settings`、`tests/ui`。

---

## 3. 分层与依赖铁律

| 层 | 允许依赖 | 禁止 |
|---|---|---|
| `core/` | 仅标准库 | import pygame、import 任何具体棋类 |
| `games/<key>/` | `core`、自己的 `geometry` | import `ai`、import `ui.sidebar/window`（`view.py` 例外） |
| `ai/` | `core.Game` 接口 | import pygame、知道任何具体棋类 |
| `ui/` | pygame、settings、`board_view` 协议 | 实现规则（**也不 import `games`**） |
| `controller/` | 全部（负责串联） | 直接绘制 |

四条支撑整个设计的约束，改动时别破坏它们：

1. **状态不可变**：`Game.apply(state, move)` 必须返回**新** `State`，绝不原地修改。
   悔棋（快照栈）、AI 搜索（树展开）、多线程读取都建立在这一点上，一旦有原地修改，
   这三处会同时出现"偶发、难复现"的错误。
2. **AI 线程绝不触碰 pygame**：搜索在后台线程跑，只通过 `AIWorker.poll()` 把结果交回主循环。
   `core` 层只传可序列化数据，将来要换 `multiprocessing` 成本很低。
3. **搜索状态放在「每次搜索一个实例」的上下文里**（`_MinimaxRun` / `_MCTSRun`），
   引擎对象本身无状态 —— 否则"取消后立刻按新参数重开"会串味。
4. **给框架加能力 = 加 `hasattr` 探测的可选钩子**，而不是给已有棋类改代码。
   摄像机就是这么加进去的：`ui/camera.py` 属于框架层，另外三个棋类**一行都没改**。

---

## 4. 核心抽象（`core/`）

### `State` —— 局面

```python
class State(ABC):
    @property
    def current_player(self) -> int: ...      # 该谁走（玩家索引 0/1）
    def is_terminal(self) -> bool: ...        # 必须 O(1)：rollout 循环里每步都调
    def winner(self) -> int | None: ...       # 返回玩家索引，不是棋子值
    def zobrist_hash(self) -> int: ...        # 置换表 / MCTS 节点复用
```

### `Move` —— 着法

```python
@dataclass(frozen=True, slots=True)
class Move(ABC):
    player: int
    is_placement: bool = False                # 框架级通用属性：放置型着法
```

必须是**可哈希**的（`frozen=True`）—— MCTS 要拿它当字典键去重与统计。

### `Game` —— 规则引擎（唯一的扩展契约）

| 方法 | 职责 |
|---|---|
| `initial_state()` | 初始局面 |
| `legal_moves(state, options=None)` | `options is None` → **全部**着法（UI 用）；否则按 `options` 裁剪 + 排序（搜索用） |
| `is_legal(state, move)` | 单步校验（UI 兜底与契约测试） |
| `apply(state, move)` | 返回**新**状态 |
| `evaluate(state, player, weights)` | 以 `player` 为视角的静态评估分 |
| `rollout_move(state, rng, options, weights)` | MCTS rollout 的默认策略 |

外加两类 **ClassVar 元数据**（纯数据，UI 负责画）：

- **接进系统用**：`key`、`display_name`、`settings_map`（settings 键 → 构造参数名）。
- **接进界面用**：`tagline` / `summary` / `goal` / `rules` / `howto` / `tips` / `icon`。
  大厅卡片与规则浮层**全部从这里取**，所以接新棋类时大厅零改动。

### `SearchOptions` —— 搜索期的裁剪旋钮

```python
SearchOptions(max_branch=16, order=True, include_special=True, include_walls=True)
```

- **`max_branch`**：组合爆炸型着法的候选上限（如墙位）。**只对真正需要的棋类有意义**。
- **`include_walls` / `include_special`**：墙棋专用（是否生成墙分支 / 是否生成跳跃类着法）。
  其它棋类**一律忽略**。
- **`order`**：是否按启发式排序。**它和 `max_branch` 是一对** —— 见坑清单第 4 条。

### `GameRegistry` —— 插件式接入点

`key -> (Game 实例, view_factory)`。`register(game)` 注册规则，`register_view(key, factory)`
单独注册视图（这样 `core` 不必 import 任何 UI 代码）。

### `BoardView` —— 棋盘视图协议（`ui/board_view.py`）

```python
layout(area)                                      # 按可用区域重算布局
draw(surface, fonts, game, state, view, *, interactive)
handle_click(pos, game, state, view) -> Move|None  # 点击 -> 着法
handle_motion(pos, game, state, view)              # 悬停高亮 / 幽灵预览
animate(move, duration_ms) / update(dt_ms) / is_animating() / reset() / set_last_move(move)
```

规则是"墙棋的槽位、围棋的点、国象的格子差异太大"，所以**不做通用棋盘渲染器** ——
只共享侧栏 / 控件 / AI 调度 / 场景，棋盘各写各的。

---

## 5. AI 子系统（`ai/`）

**只有一套接口，两个可用算法，按 `key` 注册。**

- `AIEngine.search(game, state, params, ctx) -> SearchResult`
- `SearchContext`：真实时限 + `threading.Event` 取消开关。**时限与取消必须在搜索内部
  被频繁检查**，否则"改了参数想立刻重搜"要等旧搜索跑完。
- `AIWorker`：把 `search` 丢进后台线程，`poll()` 返回"有没有结果"。UI 只调 `poll()`。

| 引擎 | 算法 | 适合 |
|---|---|---|
| `MinimaxEngine` | 负极大值 + Alpha-Beta + 迭代加深 + Zobrist 置换表 | 分支可控的棋类；靠剪枝扛住组合爆炸 |
| `MCTSEngine` | UCB1 选点 + 惰性展开 + 启发式 rollout | 评估函数不好写 / 分支极大的棋类 |
| `RandomEngine` | 均匀随机 | 兜底与基准 |

实测吞吐（用于判断该给哪个棋类推荐哪个引擎）：

| 棋类 | MCTS 迭代/秒 | 备注 |
|---|---|---|
| 重力四子棋 | ~2090 | Minimax 与 MCTS 都能下好 |
| 步步为营 | ~590 | Minimax depth 4 ≈ 80ms |
| 大力士棋 | ~180 | 建议候选上限 20~32 |
| 昆虫棋 | **~83** | 优先用 Minimax（d4~6，候选 16~32） |

---

## 6. UI 子系统（`ui/`）

### 场景

`Scene` 是一个 Protocol：`on_enter / on_exit / layout / handle_event / update / draw`。

- `GameWindow` **只**是窗口宿主：screen、clock、QUIT / VIDEORESIZE、设置落盘、场景切换。
  其余全部下发给当前 scene。
- 两个场景：`LobbyScene`（卡片网格）↔ `MatchScene`（棋盘 + 侧栏 + 结算浮层）。
- **`GameWindow` 用转发 property 把 `session` / `view` / `sidebar` / `view_state` 等
  转发给 `match`**，因此既有测试可以继续写 `window.session`。这是"场景重构不炸测试"的关键。
- 回大厅时 `MatchScene.on_exit` 必须先 `session.cancel_thinking()`，
  否则后台 AI 线程会拿着旧局面继续跑。

### `MatchScene` 每帧做什么

1. 把 `area` / `sidebar_rect` / `board_area` 交给侧栏与视图 `layout()`；
2. `session.poll()` 收 AI 结果；
3. 转发鼠标事件给视图（拖拽 / 点击由摄像机或视图自己裁决）；
4. `view.update(dt)` 推进动画；动画中锁定输入；
5. 画棋盘 → 画悬浮提示胶囊（宽度**自适应文字**）→ 画侧栏 → 结算浮层。

### 侧栏

`ParamSpec`（`settings/schema.py`）驱动一切：控件生成、显示/隐藏、JSON 校验与持久化。

三个可见性条件：**`games=`（按棋类）**、`needs_ai`、`needs_engine`（按是否/哪个引擎参战）。

> **新增侧栏参数忘了打 `games=(key,)`，它就会在别人的侧栏里露出来。**
> 权重键还要额外加进 `WEIGHT_KEYS`（那是个字面量 tuple，忘了加则滑块改了完全无效）。

侧栏头部固定显示"双方信息"，不参与滚动；参数区可滚动。数值框可以直接键入数值
（编辑期间键盘事件被侧栏接管，不会触发新局 / 悔棋）。

### 摄像机（`ui/camera.py`）

为**无边界棋盘**准备的通用能力，只有昆虫棋在用：

- 变换 `screen = world * scale + offset`；`zoom_at()` 以光标下的世界点为锚点缩放。
- `CameraController` 裁决"点击还是拖拽"（按累计位移，`DRAG_SLOP = 4px`），
  少了它"手抖一下"就会先平移画布再误落子。
- 视图侧全是可选钩子：`camera` / `camera_viewport()` / `world_bounds(state)` /
  `auto_fit_camera(state)` / `hud_inset()` / `idle_hint()` / `hover_hint()`。
- 自动适配（`_auto_fit_camera`）三条铁律：**鼠标按下时一帧都不许动**（否则点击被静默吞掉）、
  **内容还在视口里就别动**、**`AUTO_FIT_MAX_SCALE = 1.0` 只缩不放**。

### 动画

`BounceTween`（`ui/animation.py`）用**固定子步（1/240 秒）积分运动方程**模拟自由落体 →
触底回弹 → 阻尼衰减，重力按落差归一化。要点：掉帧或切后台回来不会炸开、底部与顶部落子的
观感一致、超时兜底放在子步循环之外。`duration_ms == 0` 表示不播放（四个棋类统一约定）。

---

## 7. 设置系统（`settings/`）

- `schema.py` 里一张 `SPECS` 表描述所有可调参数；**加一个参数 = 加一行**。
- `store.py` 负责读写 `config/settings.json`（`config/` 里的用户配置不进版本控制）。
- 优先级：**命令行覆盖（`set_volatile`，不写回文件）> 配置文件 > spec 默认值**。
  `--fast-ai`、`--mode`、`--game` 这类都走 volatile。
- `RESTART_KEYS`（`ui/match_scene.py`）里的键改动后会**重开一局** ——
  忘了把"棋盘尺寸""起始布局"这类键加进去，会出现"棋盘还是旧布局、着法已按新布局算"。

---

## 8. 测试体系

```
uv run pytest              # 全部
uv run pytest tests/games  # 只跑规则
uv run pytest tests/ai     # 只跑 AI 契约
uv run pytest tests/ui     # UI 冒烟（SDL dummy 驱动，不需要显示器）
uv run ruff check src tests scripts
```

- **规则测试**：逐条锁规则（合法性、边界、胜负、平局、哈希一致性、评估对称性）。
- **AI 契约测试**：每个棋类都要过同一套 —— 永远返回合法着法、时限生效、可复现、
  可取消、"非终局但无处可走"时必须给出着法而不是 `None`。
- **UI 测试**：用 `tests/ui/conftest.py` 的 `make_window` 夹具（SDL dummy 驱动）+
  `tests/ui/helpers.py` 的事件构造器。驱动方式：`pygame.event.post(...)` 然后
  `window._handle_events()`（无参数）。
- **渲染类 bug 用断言数据结构的测试永远抓不到**，必须"画一帧再取像素"
  （`surface.get_at(...)`）。四子棋图标、大力士棋棋子颜色、昆虫棋皇冠 / 落点绿环都这么测。

---

## 9. 四个棋类的横向对照

| 维度 | quoridor | connect4 | abalone | hive |
|---|---|---|---|---|
| 棋盘 | 9×9 方格 | 7×6 方格 | 六边形 61 格 | **无边界**（Pos→栈） |
| 状态存法 | 双方位置 + 墙集合 + 剩余墙数 | `heights` 列高 + 格子数组 | 61 格数组 + 出局计数 | dict[Pos, 栈] + 手牌推导 |
| `zobrist_hash` | 位置 + 墙（增量） | 格子（增量） | 格子（增量） | 棋子集合 + **平移归一化** |
| 用 `max_branch` | 是（限制墙候选） | 否 | **是**（开局 44~80 步） | 是（候选 16~32 更划算） |
| 用 `include_walls` | 是 | 忽略 | 忽略 | 忽略 |
| 放置模式 | 有（右键） | 无 | 无 | 无 |
| 显式 pass | 无 | 无 | 无 | **有**（一枚棋都动不了时） |
| 摄像机 | 无 | 无 | 无 | **有** |
| 动画 | 走子淡入 | 弹跳下落 | 滑动 | 走子 / 抬升 |
| 视图行数 | 495 | 374 | 477 | 1193 |

---

## 10. 坑清单（跨棋类通用，按严重度）

1. **`State.winner()` 返回玩家索引 0/1，不是棋子值 1/2**；缓存胜者的字段只能叫
   `winner_player`（叫 `winner` 会遮蔽 ABC 的方法）。
2. **调色板索引一律玩家号 0/1**（`theme.PLAYER_COLORS` 只有 2 项）。写成"棋子值"会让
   玩家 2 的悬停 / 赢棋高亮直接 `IndexError`。
3. **`include_walls` / `include_special` 是墙棋专用，其它棋类必须忽略**；
   把 `include_walls` 当成"裁剪着法"会让深度 ≥2 的节点只剩 ≤1 个着法，棋力崩掉且查不出原因。
4. **`max_branch` 是"从列表头部截断"，所以截断必须隐含排序**。
   MCTS 传的是 `order=False`，此时被裁掉的是生成顺序靠后的那批 ——
   大力士棋的生成顺序是"先单子后 2/3 连子"，不排序直接截断等于把**推挤类着法系统性砍光**。
5. **`is_terminal()` 必须覆盖"该方无处可走"**：要么像昆虫棋那样**显式生成 `PassMove`**，
   否则 MCTS 的 rollout 会一直向空着法表索取着法直到抛错，而 `AIWorker._run` 会吞掉异常 ——
   用户看到的现象是"AI 突然不下棋了"。
   反过来 `is_terminal()` 本身必须 **O(1)**，绝不能在里面跑着法生成。
6. **渲染类 bug 用断言数据结构的测试永远抓不到**，必须"画一帧再取像素"。
7. **叠层棋类的"一格"是 `tuple`**：能动 / 能选的永远是**栈顶**；
   所有判定走 `owner_at()`（= 栈顶归属），别单独特判某个虫种。
8. **无边界棋类的局面哈希要先做平移归一化**，否则置换表与 MCTS 节点复用全部失效。
9. **摄像机自动适配三条铁律**（见 §6）一条都不能少。
10. **"无边框"和"不显示窗口"是两个开关**：前者 `--frameless`（`NOFRAME` + 自绘标题栏，
    窗口照常能玩），后者 `--offscreen`（dummy 驱动，给 CI 用）。
11. **`Game` 上的 UI 元数据一律 `getattr` 取**：`goal` / `summary` / `rules` / `howto` /
    `tips` / `tagline` 都是可选 ClassVar，缺一个该降级显示而不是崩。
12. **播放动画拿到的永远是"走完之后"的局面**（先 `view.animate(move)` 再 `session.play(move)`），
    所以 Move 里给视图用的目标格信息必须是**目标格语义**，不能给源格。

---

## 11. 一些刻意的取舍

- **棋盘渲染不做通用化**：棋类间差异太大，强行统一反而难维护。共享侧栏 / 控件 / AI 调度，
  棋盘各写各的。六边形几何是纯数学，放 `games/<key>/geometry.py`，不碰 pygame。
- **AI 用线程而不是进程**：纯 Python 搜索会与主循环争 GIL，但主循环大部分时间在等待，
  实测 60 FPS 稳定。
- **用断言而不是"聪明的抽象"**：框架层写成 `hasattr` 探测 + 默认降级，
  而不是要求所有棋类都实现一堆空方法。
- **大厅卡片只放"图标 + 名称 + 副标题 + 一行简介"**：完整的规则进可滚动的浮层。
  卡片上塞进去的规则必然是删减版，而删减过的规则等于没规则。
- **卡片图标画的是「局面切片」而不是抽象棋盘**：96px 里"三连 + 空一格"比点阵网格好认得多。
