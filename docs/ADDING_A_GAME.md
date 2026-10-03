# 新增一个棋类 · 实操指南

> 目标：**只写"规则"和"棋盘怎么画"，其余全部复用**。
> 全流程大约 6 个文件 + 3 处注册，写完跑一次测试就能进大厅。
> 架构背景见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

约定：下面用 `<key>` 表示新棋类的短名（如 `othello`），它会成为注册键、命令行参数值、
目录名与侧栏过滤标记，**一旦定下别改**（配置持久化按它存）。

---

## 0. 动手之前：先想清楚这五件事

写代码之前先把下面这张表填完，能省掉大部分返工。四个已有棋类就是按这张表长出来的：

| 问题 | 为什么关键 |
|---|---|
| **棋盘是什么拓扑？** 方格 / 六边形 / 无边界 / 叠层 | 决定 `state` 的数据结构与 `geometry.py` 要不要写 |
| **一次"着法"最少需要几个字段？** | 决定 `Move` 的形状。**必须能放进 `frozen dataclass`** |
| **分支因子多大？** 开局和典型中局各多少 | 决定要不裁剪（`max_branch`）、AI 要选哪个引擎 |
| **会不会出现"非终局但无处可走"？** | 会 → 必须显式生成 `PassMove`，否则 MCTS 会静默挂掉 |
| **局面怎么压缩成一个整数？** | `zobrist_hash` 必须能以增量方式维护，否则搜索慢到不可用 |

---

## 1. 规则层：`src/boardgames/games/<key>/`

### 1.1 `state.py` —— 不可变局面

```python
"""<棋类名>局面。"""
from __future__ import annotations
from dataclasses import dataclass, replace
from boardgames.core.state import State


@dataclass(frozen=True, slots=True)
class OthelloState(State):
    cells: tuple[int, ...]          # 棋子值：0 空 / 1 玩家1 / 2 玩家2
    current: int = 0                # 玩家索引 0/1
    ply: int = 0
    winner_player: int | None = None   # ⚠️ 不能叫 winner，会遮蔽 State.winner()

    @property
    def current_player(self) -> int:
        return self.current

    def is_terminal(self) -> bool:
        return self.winner_player is not None or not self._has_move()

    def winner(self) -> int | None:
        return self.winner_player

    def zobrist_hash(self) -> int:
        ...
```

三条硬性要求：

1. **`frozen=True`**，且 `apply` 用 `dataclasses.replace` 返回新对象。
   需要列表就用 `tuple`，需要映射就用只读视图。
2. **`is_terminal()` 必须 O(1)** —— 它在 rollout 循环里每步都跑。
   胜负 / 和棋请在 `apply` 里算好存进局面（缓存成标量），不要在 `is_terminal` 里跑着法生成。
3. **胜负缓存字段叫 `winner_player`**，值域是**玩家索引 0/1**（不是棋子值 1/2）。

再补一个模块级 `initial_state(...)` 工厂，`Game.initial_state` 直接转调它。

### 1.2 `move.py` —— 着法

```python
@dataclass(frozen=True, slots=True)
class PlaceMove(Move):
    index: int
```

- **必须 `frozen=True`**（MCTS 拿它当字典键）。
- `player` 是 `Move` 基类上的字段，不用重复声明。
- 若是"放置型"着法（放墙、放子这类非移动），置 `is_placement = True`
  —— 框架靠这个通用属性决定"放完是否退出放置模式"。
- 一个着法若包含多个棋子（如大力士棋的整组推挤），
  用元组字段把整组装进去，别拆成多次 `apply`。

### 1.3 `rules.py` —— `Game` 子类（核心）

```python
class OthelloGame(Game[OthelloState, Move]):
    key = "othello"
    display_name = "黑白棋"

    # settings 键 -> 构造函数参数名（只写真正读的设置；不读就留空 dict）
    settings_map = {"othello_size": "size", "first_player": "first_player"}

    # ---- 大厅卡片与规则浮层的元数据（全部是纯数据）----
    tagline = "Othello · 翻转棋子"
    summary = "一句话简介，会显示在大厅卡片上。"
    goal = "一句话胜负条件"                       # 浮层「目标」
    rules = ("完整规则第 1 条", "第 2 条", "……")   # 浮层「规则」，可滚动，写全
    howto = ("鼠标怎么点 / 键盘怎么按",)          # 浮层「操作」
    tips = ("上手小贴士",)                        # 浮层「提示」，可为空
    icon = "dots"   # "board" | "drop" | "dots" | "hex" | "hive"

    def __init__(self, size: int = 8, *, first_player: int = 0) -> None:
        self.size = int(size)
        self.first_player = first_player

    # ---- 八个必需方法：2 个基本信息 + 6 个规则 / 评估 ----
    def player_count(self) -> int: return 2
    def player_meta(self) -> list[PlayerMeta]: ...
    def initial_state(self, first_player: int | None = None) -> OthelloState: ...
    def legal_moves(self, state, options: SearchOptions | None = None) -> list[Move]: ...
    def is_legal(self, state, move) -> bool: ...
    def apply(self, state, move) -> OthelloState: ...
    def evaluate(self, state, player, weights=None) -> float: ...
    def rollout_move(self, state, rng, options=None, weights=None) -> Move: ...

    # ---- 可选钩子（默认空实现）----
    def describe_state(self, state) -> str: ...    # 状态栏文案
    def move_hints(self, state) -> dict: ...       # 给 UI 的提示数据
```

`rules` 请按**写给玩家看的完整规则**来写 —— 卡片上只显示 `summary` 一行，
这些条目进的是可滚动的规则浮层，不受空间限制。删减过的规则等于没规则。

**`player_meta()` 的颜色用 RGB 字面量**，不要 import `ui.theme`（core/games 不得依赖 pygame 侧模块）。

### 1.4 `legal_moves` 的 `options` 语义 —— 最容易写错的一处

```python
def legal_moves(self, state, options=None):
    moves = self._all_moves(state)

    if options is None:
        return moves               # UI 用：返回全部

    # 搜索用：只有"组合爆炸型"棋类才需要下面这段
    if options.max_branch and len(moves) > options.max_branch:
        moves.sort(key=self._heuristic_key)          # ⚠️ 截断前必须先排序！
        moves = moves[: options.max_branch]
    return moves
```

| `options` 字段 | 谁在用 | 你该怎么处理 |
|---|---|---|
| `max_branch` | 只有墙棋、大力士棋、昆虫棋 | 分支小就直接忽略它 |
| `include_walls` | **墙棋专用** | 其它棋类**必须忽略**（当成"裁剪着法"会让棋力崩掉） |
| `include_special` | 墙棋专用 | 同上 |
| `order` | 所有棋类 | `True` 时按启发式排序（排序更慢但更好） |

> **`max_branch` 是"从列表头部截断"，所以截断必须隐含排序。**
> MCTS 传的是 `order=False`，若不排序直接截断，被砍掉的就是生成顺序靠后的那批。
> 大力士棋的生成顺序是"先单子、后 2/3 连子"，不排序直接截断等于把推挤类着法系统性砍光。

### 1.5 `heuristic.py` —— 评估函数

- `evaluate(state, player, weights)` 必须满足**反对称性**：
  `evaluate(s, 0, w) == -evaluate(s, 1, w)`。每个棋类都有回归用例锁这一条。
- 权重从 `weights` 里按 key 取，缺 key 用模块内默认值；不认识的键直接丢掉。
- 结构预计算（中心权重表、方向表、连通块等）用 `functools.lru_cache`。
- **别把评估分调到 `|score| > 1500`** —— MCTS 的回报要过 `tanh(score / 600)`，
  超过之后会被拍平成 ±1，梯度全丢。

### 1.6 `geometry.py` / `layouts.py`（按需）

- `geometry.py`：棋盘几何换算、直线表、BFS 距离场。**纯数学，不 import pygame**。
- `layouts.py`：固定起始布局，写成模块级常量（`settings/schema.py` 会直接引用它生成下拉选项）。

### 1.7 `view.py` —— 棋盘视图

实现 `ui/board_view.py` 的 `BoardView` 协议：

```python
class OthelloView:
    def __init__(self, ...):
        self.origin = (0, 0)   # ⚠️ 属性名不能改：测试的 pos_for() 依赖
        self.cell = 40         # ⚠️ 同上

    def layout(self, area: pygame.Rect) -> None: ...
    def draw(self, surface, fonts, game, state, view, *, interactive) -> None: ...
    def handle_click(self, pos, game, state, view) -> Move | None: ...
    def handle_motion(self, pos, game, state, view) -> None: ...
    def animate(self, move, duration_ms) -> None: ...
    def update(self, dt_ms) -> bool: ...
    def is_animating(self) -> bool: ...
    def reset(self) -> None: ...
    def set_last_move(self, move) -> None: ...

    # 没有"放置模式"就必须显式返回 False（见下）
    def in_placement_mode(self) -> bool:
        return False
```

**必须保留 `origin` 与 `cell` 两个属性名**，`tests/ui/helpers.py:pos_for()` 依赖它们。

**没有"放置模式"的棋类，务必实现 `in_placement_mode() -> False`。**
`MatchScene` 用 `hasattr` 探测这个钩子，缺了它会被当成"支持放置模式"，
右键进模式后按 `V` 会调用不存在的 `flip_orientation()` 直接崩。

**可选钩子**（用 `hasattr` 探测，不实现就走默认）：

| 钩子 | 作用 |
|---|---|
| `hover_hint()` / `hud_hint()` / `idle_hint()` | 专属提示文案。**建议 ≤ 20 汉字**（提示胶囊宽度自适应，太长会挤满棋盘） |
| `camera`（`ui.camera.Camera` 实例） | 挂上就白拿滚轮缩放 / 拖拽平移 / `F` 回正 |
| `camera_viewport()` | 收窄视口（把底部手牌条排除在拖拽区外） |
| `world_bounds(state)` | 内容包围盒，供摄像机自动适配 |
| `auto_fit_camera(state)` | 自定义自动适配的边距与缩放上限 |
| `hud_inset()` | 给底部提示让位 |
| `in_placement_mode()` | 放置模式开关（见上） |

**动画约定**：`duration_ms == 0` 表示不播放。`view.animate(move)` 在 `session.play(move)`
**之前**调用，所以拿到的是"走完之后"的局面 —— Move 里给视图用的目标格信息必须是
**目标格语义**，不能给源格。

---

## 2. 注册：三处

### 2.1 规则引擎 → `core/registry.py`

```python
def build_default_registry() -> GameRegistry:
    from boardgames.games.othello.rules import OthelloGame
    ...
    registry.register(OthelloGame())      # ← 加这一行
    return registry
```

### 2.2 视图工厂 → `app.py`

```python
def register_builtin_views(registry: GameRegistry) -> None:
    from boardgames.games.othello.view import make_view as othello_view
    ...
    registry.register_view("othello", othello_view)
    _HOVER_SIMS["othello"] = _hover_othello   # 可选：让 --hover 截图能用
```

`register_view` 要求**先注册游戏再注册视图**（key 必须先存在）。

### 2.3 侧栏参数 → `settings/schema.py`

```python
ParamSpec("othello_size", "棋盘尺寸", "int", 8, 6, 12, 1, group="game", games=("othello",))
```

**`games=(key,)` 忘了打，这个参数就会在别的棋类的侧栏里也露出来。**
若是权重类参数，还要把键加进同一文件里的 `WEIGHT_KEYS`
（那是个**字面量 tuple**，忘了加的话滑块拖了完全不生效）。

`group` 决定它出现在哪：`game` / `players` / `minimax` / `mcts` 在侧栏，
`eval`（权重）与 `ui`（界面与操作）收在「设置」浮层（`sidebar.PANEL_GROUPS`）。
两组都有按棋类过滤，标了 `games=` 就自动生效，**不需要改浮层的代码**。

需要**改动即重开一局**的参数，把 key 加进 `ui/match_scene.py` 的 `RESTART_KEYS`：

```python
RESTART_KEYS = {..., "othello_size"}
```

忘了加会出现"棋盘还是旧布局、着法已经按新布局算"。

---

## 3. 侧栏玩家行（唯一需要改"别人的代码"的地方）

`MatchScene._player_details(state, walls)` 给每个棋类定制侧栏顶部玩家行的数值文案：

```python
def _player_details(self, state, walls) -> tuple[str, str]:
    if self.game_key == "othello":
        return (f"{state.count(0)} 子", f"{state.count(1)} 子")
    ...
```

不加分支就会走通用回退分支，显示成"墙 0"（昆虫棋当初就吃过这个亏）。
返回的两段**只放数值部分**，类型标签由侧栏自己拼。

---

## 4. 验证清单

```bash
uv run ruff check src tests scripts                  # 必须 All checks passed
uv run pytest -m "not slow"                          # 先跑快的（几秒，改一点跑一次）
uv run pytest                                        # 提交前跑全量（约 40 秒）
uv run boardgames --game othello                     # 能进大厅 → 能进对局
uv run boardgames --game othello --scene match --hover <你的悬停模式> --offscreen \
    --screenshot /tmp/o.png --demo 20                # 拍一张中局图看一眼
```

> 跑真 AI 搜索与整局 rollout 的用例会自动打上 `slow`（见 `tests/conftest.py`），
> 所以日常迭代用 `-m "not slow"`；**只有动到规则、评估函数或引擎时才跑全量**。

### 测试要写什么

放在 `tests/games/<key>/`，**文件名必须是 `test_*.py`**
（pytest 默认只收集这个前缀 —— 项目里已有一批 `c4_test_*.py` 因此从未被运行过）。

测试目录的公用件：

- 造局面：写一个 `make_state({坐标: 值}, ...)` 之类的辅助函数，**按坐标写、其余自动填充**，
  不要去手写棋盘图的字符串（极易抄错）。
- **跨测试目录 import 的文件名不能重名**（pytest 把每个测试目录都插进 `sys.path` 且没有
  `__init__.py`，两个 `helpers.py` 会互相覆盖）。按棋类起名，如 `oth_helpers.py`。
- UI 侧直接用 `tests/ui/conftest.py` 的 `make_window` 夹具与 `tests/ui/helpers.py`。

必须覆盖的几类：

1. **规则逐条**：每个合法性约束各写一条用例；边界值（第一行/最后一行、满盘、无子可走）。
2. **`zobrist_hash`**：同一局面（不同构造路径）哈希相同；走一步再退回来哈希复原。
3. **评估反对称性**：随手搜索若干局面，断言 `evaluate(s,0) == -evaluate(s,1)`。
4. **AI 契约**（`tests/ai/`）：把已有棋类的契约测试抄一份换成你的 key ——
   引擎永远返回合法着法、时限生效、可复现、可取消；
   **"非终局但无处可走"的局面下，四个引擎都必须交出 `PassMove` 而不是 `None`**。
5. **画一帧再取像素**：渲染类 bug 用断言数据结构的测试**永远抓不到**。
   `surface.get_at(pos)` 验证棋子颜色（玩家索引 0/1 写成棋子值 1/2 会 `IndexError`）、
   棋盘上确实有那么多枚子、目标格提示画在棋子之上。

`--hover` 的悬停模拟器写在 `app.py` 的 `_hover_<key>()` 里，用
`view.handle_click(pos, game, state, view_state)` + `view.handle_motion(...)` 摆姿势。

---

## 5. 坑清单（新棋类专属）

按踩坑概率排序，前四条基本每个新棋类都会遇到：

1. **`is_terminal()` 没覆盖"该方无处可走"** → MCTS 的 rollout 会向空着法表一直索取着法
   直到抛错，而 `AIWorker._run` 会吞掉异常。**现象是"AI 突然不下棋了"**，
   而且不打日志，极难定位。有这种局面就显式生成 `PassMove`（昆虫棋就是这么做的）。
2. **调色板索引写成了棋子值** → `theme.PLAYER_COLORS` 只有 2 项，索引 2 直接 `IndexError`。
   记住：**着色一律用玩家索引 0/1，判定才用棋子值 1/2**。
3. **把 `include_walls` 当成通用的"裁剪着法"开关** → 深度 ≥2 的节点只剩一个着法，
   棋力崩掉但没有任何报错。
4. **`max_branch` 截断前没排序** → 系统性砍掉某一类着法（见 §1.4）。
5. **`winner` 字段名遮蔽 `State.winner()`** → 缓存字段必须叫 `winner_player`。
6. **无边界棋类的哈希没做平移归一化** → 整体平移是同一局面，不归一化会让置换表与
   MCTS 节点复用全部失效（表现是"AI 想很久还下得很差"）。
7. **叠层棋类没统一走"栈顶归属"判定** → 能动 / 能选的永远是栈顶那一枚，
   别为某个特殊棋种单独写分支。
8. **视图没保留 `origin` / `cell` 属性名**，或没实现 `in_placement_mode() -> False`。
9. **侧栏参数漏了 `games=` / `WEIGHT_KEYS` / `RESTART_KEYS`** 三处之一。
10. **`_player_details` 没加分支** → 侧栏显示成"墙 0"。

---

## 6. 一次新增的改动清单（模板）

```
新增：
  src/boardgames/games/<key>/__init__.py
  src/boardgames/games/<key>/state.py
  src/boardgames/games/<key>/move.py
  src/boardgames/games/<key>/rules.py
  src/boardgames/games/<key>/heuristic.py
  src/boardgames/games/<key>/view.py
  (按需) geometry.py / layouts.py / assets/
  tests/games/<key>/test_*.py
  tests/ai/test_<key>_contract.py

修改（都是加行，不改逻辑）：
  src/boardgames/core/registry.py     build_default_registry() 加一行
  src/boardgames/app.py               register_builtin_views() 加一行（+ 可选悬停模拟）
  src/boardgames/settings/schema.py   SPECS 加若干 ParamSpec（标 games=），
                                      权重键加进 WEIGHT_KEYS
  src/boardgames/ui/match_scene.py    _player_details() 加一个分支；
                                      重开类参数加进 RESTART_KEYS
```

**不需要改**：侧栏、主题、控件、动画、摄像机、AI 引擎、AI 调度线程、悔棋、
游戏大厅、规则浮层、设置持久化。这就是这个框架存在的意义。
