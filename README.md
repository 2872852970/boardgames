# 棋类游戏（boardgames）

用 **Python + Pygame** 写的桌面棋类游戏框架，内置两个游戏：
**步步为营（墙棋 / Quoridor）** 与 **重力四子棋（Connect Four）**。

项目从第一天就按「可插拔」设计：规则、AI、界面三层解耦，后续接入新的棋类只需实现
规则引擎 + 一块棋盘视图，**AI、侧栏、主题、大厅全部自动复用**。

---

## 快速开始

需要 [uv](https://docs.astral.sh/uv/)（Python 3.13）。

```bash
uv sync              # 安装依赖（含 pygame-ce）
uv run boardgames    # 启动（先进游戏选择大厅）
uv run pytest        # 运行测试
```

常用参数：

```bash
uv run boardgames --game connect4                 # 直接进四子棋对局
uv run boardgames --scene match                   # 跳过大厅，直接进对局
uv run boardgames --game connect4 --cols 8 --rows 7   # 自定义四子棋盘
uv run boardgames --game quoridor --size 11 --walls 15   # 自定义墙棋棋盘
uv run boardgames --mode eve --p1 mcts --p2 minimax       # AI 自对弈
uv run boardgames --window 1000x640               # 强制窗口尺寸（小屏/调试布局）
uv run python scripts/benchmark_ai.py             # AI 性能基准
```

无头截图（自检 / 看布局用）：

```bash
uv run boardgames --headless --screenshot lobby.png --scene lobby
uv run boardgames --headless --screenshot c4.png --game connect4 --scene match --demo 8 --hover drop
uv run boardgames --headless --screenshot q.png  --game quoridor  --scene match --demo 6 --hover wall-h
```

> 窗口默认 1180×780，但会自动裁剪到不超过你的屏幕可用区域（小屏或高 DPI 缩放下也不会
> 把底部按钮挤出去）。窗口可自由缩放，侧栏在小窗口下会自动收窄，侧栏内容可滚动。

---

## 游戏选择大厅

启动后先进大厅：**一张卡片一个游戏**，含示意图标、玩法要点，鼠标悬停高亮、点击进入对局。

- 也支持键盘：`←↑↓→` 选择、`Enter` 确认、`Esc` 退出。
- **卡片数据来自代码**：每个 `Game` 类自带 `tagline` / `summary` / `rules` / `icon` 元数据，
  大厅遍历注册表自动生成 —— **以后接第三个棋类，大厅这边零改动**。
- 窗口小到放不下时会自动启用滚轮。

---

## 玩法（步步为营）

9×9 棋盘，双方各持 **10 面墙**。棋子放在自己这一侧底边的中央格，目标是**先走到对方底线**。

每回合二选一：

| 行动 | 说明 |
|---|---|
| 移动棋子 | 上下左右走一格，不能斜走；不能穿墙，只能绕行 |
| 放置围墙 | 墙长 2 格，横竖皆可，用来挡住对手 |

**跳跃**：双方棋子正面相邻时可以跳过对方，落在其正后方；若正后方被墙（或棋盘边界）挡住，
可以改跳到对方的左侧或右侧。

**放墙限制**：

- 不能与已有墙重叠（同向相邻锚点会共用一段边，也算重叠）；
- 不能与已有墙交叉成「十」字（**严格规则**，两端相接的 L / T 形合法）；
- 放墙后**双方都必须仍有路能走到各自目标行**，否则这面墙非法；
- 墙用完后只能移动棋子。

> 数字版里「石头剪刀布定先后」被替换成开局可选先手（默认玩家 1 先手，也可设为随机）。

## 玩法（重力四子棋）

标准 **7 列 × 6 行 = 42 格**，双方各 21 枚棋子。列数 / 行数可在侧栏调整（5-12 列 / 4-10 行），
**连线数固定 4**。

- 每回合把一枚己方棋子投进**任一未满的列**，棋子**因重力落到该列最低的空位**；
- 横 / 竖 / 斜**任一方向连续四子**即获胜；
- 棋盘填满仍无人连成四子则**平局**。

**落子动画**是真的物理模拟：自由落体 → 触底回弹 → 阻尼衰减，用固定子步（1/240 秒）
积分运动方程，所以掉帧或切后台回来都不会炸开；重力按落差归一化，底部落子和顶部落子的
观感一致。动画时长在侧栏「落子动画」里可调（默认 850ms）。

---

## 操作

**全程鼠标**。

**步步为营**靠右键切换的「放墙模式」区分两种操作：

| 模式 | 鼠标移动 | 点击 |
|---|---|---|
| **走子模式**（默认） | 高亮合法落点（含跳跃落点） | 移动棋子 |
| **放墙模式**（右键进入） | 吸附到最近的内部网格交点，画出幽灵墙：**绿色可放 / 红色不可放** | 放置该墙 |

- **右键**开 / 关放墙模式；**放下一面墙后会自动退出**（一回合本来就只放一面墙）。
- 放墙模式下**四个格子的公共交点同样有提示**。
- 横向 / 竖向的判定带有**滞回**：在某个交点选定了朝向之后，鼠标轻微抖动不会换朝向；
  只有明显朝另一条网格线移动才会切换，所以预览不会在横竖之间乱跳。想手动换朝向按 `V`。
- 棋盘外框上没有墙槽，所以只有**内部**网格线能放墙。

**重力四子棋**更简单：鼠标移到某一列就预览棋子会落到哪一格，点击即投子。

棋盘左上角实时显示当前意图（`点击走子` / `点击第 4 列（落在第 2 层）` 等）。

### 快捷键

| 键 | 作用 |
|---|---|
| `U` | 悔棋 |
| `N` | 新局 |
| `R` | 认输 |
| `V` | 放墙模式下切换横 / 竖朝向（仅墙棋） |
| `空格` | 暂停 / 继续（AI 自对弈） |
| `S` | 自对弈单步 |
| `Esc` | **三级**：退出放墙模式 → 回大厅 → （在大厅里）退出程序 |

### AI 自对弈：默认暂停 + 单步

进入 **AI 自对弈** 模式时对局**默认暂停**，方便一场一场慢慢看：

- 点侧栏的 **「单步」** 按钮，或**直接点棋盘**，推进一着；
- 点 **「暂停 / 继续」**（或按空格）切换成自动连续对弈；
- 单步走完仍然保持暂停。

### 对局模式与侧栏精简

侧栏顶部可切换 **双人对战 / 人机对战 / AI 自对弈**。参数会**按当前模式 + 当前棋类自动精简**：

| 模式 | 侧栏显示 |
|---|---|
| 双人对战 | 只有棋局设置与界面参数（AI 相关分组全部隐藏） |
| 人机 / 自对弈 | 额外显示「对局双方」与**实际参战**引擎的参数（Minimax 或 MCTS），以及评估权重 |

**参数按棋类隔离**：玩四子棋时看不到「每人墙数」「墙槽位」这类墙棋专属项，
玩墙棋时看不到「列数」「落子动画」这类四子棋专属项。侧栏标题也跟着当前棋类变。

### 悔棋规则

- 双人同屏：回退 1 步；
- 人机：一直回退到**轮到你**为止（AI 已应招则是 2 步，AI 还在思考时是 1 步），
  并且会立刻取消正在进行的搜索；
- AI 自对弈：回退 1 步并自动暂停。

---

## AI 参数（侧栏可实时调整）

所有参数改完**立刻生效**，并自动持久化到 `config/settings.json`。

- **滑块**：拖动滑轨调节；也可以**点击右侧数值框直接键入**数值
  （回车 / Tab 确认，Esc 取消，点到别处也会确认）。输入只做范围裁剪，不会按步长吸走你输入的值。
  编辑期间键盘不会触发新局 / 悔棋等快捷键。
- **双方信息**（谁执哪一方、各剩几枚棋子 / 几面墙、轮到谁）固定在侧栏顶部，滚动参数时始终可见。

| 分组 | 参数 | 适用 |
|---|---|---|
| 棋局设置 | 棋盘尺寸 / 每人墙数（墙棋）、列数 / 行数（四子棋）、对局模式、先手 | 改动会重开一局 |
| 对局双方 | 玩家 1 / 玩家 2 类型 | 人类 / Minimax / MCTS / 随机（仅人机、自对弈） |
| Minimax | 搜索深度、考虑放墙的层数、墙候选上限、思考时限、置换表 | 墙棋的层数与候选上限只对墙棋显示 |
| MCTS | 模拟次数、探索常数 C、Rollout 深度上限、墙候选上限、思考时限 | 同上 |
| 评估权重 | 墙棋：最短路径差、剩余墙数差、机动性差、节奏、走子进度差、放墙概率<br>四子棋：子数差、中心列权重、连线长度、即时威胁 | 按棋类隔离 |
| 界面 | 动画时长（四子棋落子动画）、落点提示、墙槽位显示、AI 落子停顿 | 纯观感，不影响棋力 |

> 只显示**当前模式下真正生效**的参数：双人对战时看不到 AI 分组；人机对战选了 Minimax
> 就只有 Minimax 参数，不会出现 MCTS 的项。

**两种算法的分工**（同一套 `Game` 接口，可随时对比）：

- **Minimax（Alpha-Beta）**：负极大值 + Alpha-Beta + 迭代加深 + Zobrist 置换表。
  靠两层剪枝扛住 Quoridor 巨大的墙分支：每个节点只看「对手最短路径附近」的少量墙候选，
  并且超过 `考虑放墙的层数` 层后只展开走子。
- **MCTS（UCT）**：UCB1 选点 + 惰性展开 + 启发式 rollout。
  rollout 沿**目标距离场**推进（保证单调收敛，不会来回振荡），并以「越快取胜回报越高」塑形。

改 AI 参数时若 AI 正在思考，会立刻取消并按新参数重新搜索。

---

## 项目结构

```
src/boardgames/
├── core/                  # 游戏无关抽象：Move / State / Game / GameRegistry
├── games/
│   ├── quoridor/          # 墙棋：geometry(锚点与BFS) / state / move / rules / heuristic / view
│   └── connect4/          # 四子棋：state / move / rules / heuristic / view
├── ai/                    # engine(统一接口) / minimax / mcts / tt / worker(后台线程) / random_ai
├── controller/session.py  # 对局会话：模式、悔棋、AI 编排
├── settings/              # ParamSpec 参数描述 + JSON 持久化
└── ui/
    ├── scene.py           # 场景协议
    ├── window.py          # 窗口宿主：主循环 + 场景切换
    ├── lobby.py           # 游戏选择大厅
    ├── match_scene.py     # 对局场景：棋盘 + 侧栏 + AI 调度 + 结算浮层
    └── theme / fonts / render / animation / board_view 协议 / widgets / sidebar
tests/                     # 233 项：规则、AI 契约、参数、无头 UI 冒烟
scripts/benchmark_ai.py    # AI 性能与强度基准
```

分层约定：`core` 只依赖标准库，不 import pygame；`ai` 只依赖 `Game` 接口，不知道任何具体棋类的存在；
`ui` 不实现任何规则。AI 在后台线程跑，**绝不触碰 pygame 对象**。

---

## 如何新增一个棋类

以四子棋 `connect4` 为例，完整改动如下。

1. **规则层** `src/boardgames/games/<key>/`：

   | 文件 | 内容 |
   |---|---|
   | `state.py` | `State` 子类（**不可变** + `zobrist_hash`）+ `initial_state()` |
   | `move.py` | `Move` 子类，`@dataclass(frozen=True, slots=True)`（MCTS 要拿它当字典键） |
   | `rules.py` | `Game` 子类的 6 个方法：`initial_state` / `legal_moves` / `is_legal` / `apply` / `evaluate` / `rollout_move` |
   | `heuristic.py` | `evaluate` 的实现与权重表（`lru_cache` 缓存预计算的结构） |
   | `view.py` | 棋盘视图（下条） |

   在 `Game` 子类上声明元数据，大厅会自动生成卡片：

   ```python
   class Connect4Game(Game[Connect4State, Move]):
       key = "connect4"
       display_name = "重力四子棋"
       settings_map = {"connect4_cols": "cols", "connect4_rows": "rows"}
       tagline = "Connect Four · 重力落子"
       summary = "在 7×6 的棋盘上轮流投子……"
       rules = ("任选一列投子……", "横/竖/斜任一方向连续四子即胜", "……")
       icon = "drop"     # "board" | "drop" | "dots"
   ```

   `settings_map` 是 **settings 键 → 构造参数名** 的映射，`GameSession` 靠它注入侧栏参数。

2. **棋盘视图**：实现 `ui/board_view.py` 里的 `BoardView` 协议
   （`layout` / `draw` / `handle_click` / `handle_motion` / `animate` / `update` / `is_animating` /
   `reset` / `set_last_move`）。可选实现 `hover_hint()` 与 `hud_hint()` 拿到专属提示文案。
   视图必须保留 `origin` 与 `cell` 两个属性名（UI 测试的 `pos_for()` 依赖它们）。

3. **侧栏参数**：在 `settings/schema.py` 里加 `ParamSpec`，**记得打 `games=(key,)` 标**，
   否则这些参数会在别的棋类侧栏里也露出来：

   ```python
   ParamSpec("connect4_cols", "列数", "int", 7, 5, 12, 1, group="game", games=("connect4",))
   ```

4. **注册两处**：

   ```python
   # core/registry.py
   def build_default_registry():
       registry.register(QuoridorGame())
       registry.register(Connect4Game())   # ← 加这行

   # app.py
   def register_builtin_views(registry):
       from boardgames.games.connect4.view import make_view
       registry.register_view("connect4", make_view)
   ```

侧栏、主题、控件、AI 调度、悔棋、后台搜索线程、大厅卡片全部自动复用 —— 新棋类不用重写这些。

---

## 测试

```bash
uv run pytest              # 全部（233 项）
uv run pytest tests/games  # 只跑规则
uv run pytest tests/ai     # 只跑 AI 契约
uv run pytest tests/ui     # 无头 UI 冒烟（用 SDL dummy 驱动，不需要显示器）
```

覆盖重点：放墙合法性（越界 / 重叠 / 交叉 / L·T 合法 / 双人连通性）、跳跃全分支、
重力落子、四方向四连、平局判定、评估函数对称性、rollout 必然收敛、
AI 统一契约（永远返回合法着法、时限生效、可复现、可取消）、
参数校验与持久化、参数按棋类隔离、场景切换、弹跳物理的掉帧稳定性，以及一批**回归用例**：
rollout 对局必然收敛、鼠标悬停不会折叠分组、AI 等待落子期间不重开搜索、
滑块只有按住才跟随鼠标、窗口尺寸不超出屏幕。

---

## 一些取舍

- **墙的严格规则**：默认禁止横竖墙在同一锚点交叉成「十」字。
  `QuoridorGame(allow_wall_crossing=True)` 可以放开。
- **斜跳的墙检查**：默认检查起跳棋子到斜向落点那条边是否被墙挡住，
  可用 `QuoridorGame(jump_diag_checks_wall=False)` 关闭。
- **四子棋的连线数固定 4**：只开放棋盘列 / 行数。规则更纯粹，侧栏也不会多出无意义的选项。
- **四子棋没有「节奏」权重**：墙棋里"轮到谁走"有先后优势，四子棋没有（先手优势已经体现在
  先落子的棋子上）。加这一项会破坏 `evaluate(s,0) == -evaluate(s,1)` 的对称性。
- **四子棋完全忽略 `max_branch` 与 `include_walls`**：分支因子本来就小，而 `include_walls`
  是 minimax 为墙棋的墙分支设计的开关，当成"裁剪着法"会让深度 ≥2 的节点只剩一个着法。
- **棋盘渲染不做通用化**：墙棋的槽位、围棋的点、国象的格子差异太大，
  强行统一反而难维护，因此只共享侧栏/控件/AI 调度，棋盘由各游戏自带视图实现。
- **场景用转发 property 兼容旧测试**：`GameWindow` 暴露 `session` / `view` / `_update()` 等，
  转发给当前的 `MatchScene`，因此既有测试一行都不用改。
- **AI 用线程而不是进程**：纯 Python 搜索会与主循环争 GIL，但主循环大部分时间在等待，
  实测 60 FPS 稳定。引擎接口只传可序列化数据，将来要换 `multiprocessing` 成本很低。
