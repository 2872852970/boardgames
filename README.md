# 棋类游戏（boardgames）

用 **Python + Pygame** 写的桌面棋类游戏，第一个游戏是 **步步为营（墙棋 / Quoridor）**。

项目从第一天就按「可插拔」设计：规则、AI、界面三层解耦，后续接入新的棋类只需实现
规则引擎 + 一块棋盘视图，**AI 与界面框架零改动**。

---

## 快速开始

需要 [uv](https://docs.astral.sh/uv/)（Python 3.13）。

```bash
uv sync              # 安装依赖（含 pygame-ce）
uv run boardgames    # 启动游戏
uv run pytest        # 运行测试
```

其它用法：

```bash
uv run python -m boardgames --mode eve --p1 mcts --p2 minimax   # 直接开一局 AI 自对弈
uv run python -m boardgames --size 11 --walls 15                # 自定义棋盘与墙数
uv run python -m boardgames --window 1000x640                   # 强制窗口尺寸（小屏/调试布局）
uv run python scripts/benchmark_ai.py                           # AI 性能基准
```

> 窗口默认 1180×780，但会自动裁剪到不超过你的屏幕可用区域（小屏或高 DPI 缩放下也不会
> 把底部按钮挤出去）。窗口可自由缩放，侧栏在小窗口下会自动收窄，侧栏内容可滚动。

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

---

## 操作

**全程鼠标，不需要切换任何"放墙模式"** —— 靠鼠标位置自动区分两种操作：

| 鼠标位置 | 提示 | 点击效果 |
|---|---|---|
| **格子边缘**（靠近网格线） | 吸附到最近的墙锚点，画出幽灵墙：**绿色可放 / 红色不可放** | 放置该墙 |
| **格子中心** | 高亮该落点 | 移动棋子（含跳跃） |

水平边和竖直边是分别识别的：鼠标贴近**水平**网格线就预览横墙，贴近**竖直**网格线就预览竖墙；
在交点附近两者都近时，会优先给出能放的那一种。棋盘外框上没有墙槽，所以只有**内部**
网格线能放墙。如果某个位置放不下墙、而它底下的格子刚好是合法落点，点击会退化成走子，
不会"点了没反应"。

### 快捷键（可选）

| 键 | 作用 |
|---|---|
| `U` | 悔棋 |
| `N` | 新局 |
| `R` | 认输 |
| `空格` | 暂停 / 继续（AI 自对弈时） |
| `Esc` | 退出游戏 |

### 对局模式与侧栏精简

侧栏顶部可切换 **双人对战 / 人机对战 / AI 自对弈**。参数会**按当前模式自动精简**：

| 模式 | 侧栏显示 |
|---|---|
| 双人对战 | 只有棋局设置与界面参数（AI 相关分组全部隐藏） |
| 人机 / 自对弈 | 额外显示「对局双方」与**实际参战**引擎的参数（Minimax 或 MCTS），
以及评估权重；随机走子没有可调项，此时不显示引擎分组 |

### 悔棋规则

- 双人同屏：回退 1 步；
- 人机：一直回退到**轮到你**为止（AI 已应招则是 2 步，AI 还在思考时是 1 步），
  并且会立刻取消正在进行的搜索；
- AI 自对弈：回退 1 步并自动暂停。

---

## AI 参数（侧栏可实时调整）

所有参数改完**立刻生效**，并自动持久化到 `config/settings.json`。

| 分组 | 参数 | 说明 |
|---|---|---|
| 棋局设置 | 棋盘尺寸 / 每人墙数 / 先手 | 改动会重开一局 |
| 对局双方 | 玩家 1 / 玩家 2 类型 | 人类 / Minimax / MCTS / 随机（仅人机、自对弈模式显示） |
| Minimax | 搜索深度、考虑放墙的层数、墙候选上限、思考时限、置换表 | 深度 4 + 时限 1200ms 是默认档 |
| MCTS | 模拟次数、探索常数 C、Rollout 深度上限、墙候选上限、思考时限 | 探索常数越大越偏探索 |
| 评估权重 | 最短路径差、剩余墙数差、机动性差、节奏、走子进度差、rollout 放墙概率 | 全部可自定义 |
| 界面 | 动画时长、落点提示、墙槽位显示、AI 落子停顿 | 纯观感，不影响棋力 |

> 只显示**当前模式下真正生效**的参数：双人对战时看不到 AI 分组；人机对战选了 Minimax
> 就只有 Minimax 参数，不会出现 MCTS 的项。

**两种算法的分工**（同一套 `Game` 接口，可随时对比）：

- **Minimax（Alpha-Beta）**：负极大值 + Alpha-Beta + 迭代加深 + Zobrist 置换表。
  靠两层剪枝扛住 Quoridor 巨大的墙分支：每个节点只看「对手最短路径附近」的少量墙候选，
  并且超过 `consider_wall_depth` 层后只展开走子。
- **MCTS（UCT）**：UCB1 选点 + 惰性展开 + 启发式 rollout。
  rollout 沿**目标距离场**推进（保证单调收敛，不会来回振荡），并以「越快取胜回报越高」塑形。

改 AI 参数时若 AI 正在思考，会立刻取消并按新参数重新搜索。

---

## 项目结构

```
src/boardgames/
├── core/                  # 游戏无关抽象：Move / State / Game / GameRegistry
├── games/quoridor/        # 具体游戏：geometry(锚点与BFS) / state / move / rules / heuristic / view
├── ai/                    # engine(统一接口) / minimax / mcts / tt / worker(后台线程) / random_ai
├── controller/session.py  # 对局会话：模式、悔棋、AI 编排
├── settings/              # ParamSpec 参数描述 + JSON 持久化
└── ui/                    # theme / fonts / render / animation / board_view 协议 / widgets / sidebar / window
tests/                     # 99 项：规则、AI 契约、参数、无头 UI 冒烟
scripts/benchmark_ai.py    # AI 性能与强度基准
```

分层约定：`core` 只依赖标准库，不 import pygame；`ai` 只依赖 `Game` 接口，不知道 Quoridor 的存在；
`ui` 不实现任何规则。AI 在后台线程跑，**绝不触碰 pygame 对象**。

---

## 如何新增一个棋类

1. 在 `src/boardgames/games/<key>/` 下实现：
   - `State` 子类（**不可变**，含 `zobrist_hash`）；
   - `Move` 子类（可哈希、可比较，因为要被当作字典键）；
   - `Game` 子类：`initial_state` / `legal_moves` / `is_legal` / `apply` / `evaluate` / `rollout_move`
     共 6 个方法（`SearchOptions` 用来在搜索期裁剪组合爆炸的着法）。
2. 实现一块棋盘视图（`ui/board_view.py` 里的 `BoardView` 协议：`layout/draw/handle_click/handle_motion/animate/update/reset`）。
3. 在 `app.py` 里注册两行：

```python
def register_builtin_views(registry):
    from boardgames.games.quoridor.view import make_view
    registry.register_view("quoridor", make_view)
```

`core.registry.build_default_registry()` 里加一行 `registry.register(你的Game())` 即可。

侧栏、主题、控件、AI 调度、悔棋、后台搜索线程都是共用的 —— 新棋类不用重写这些。

---

## 测试

```bash
uv run pytest              # 全部
uv run pytest tests/games  # 只跑规则
uv run pytest tests/ai     # 只跑 AI
uv run pytest tests/ui     # 无头 UI 冒烟（用 SDL dummy 驱动，不需要显示器）
```

覆盖重点：放墙合法性（越界 / 重叠 / 交叉 / L·T 合法 / 双人连通性）、跳跃全分支、
胜负判定、AI 统一契约（永远返回合法着法、时限生效、可复现、可取消）、
参数校验与持久化、以及一批**回归用例**：rollout 对局必然收敛、鼠标悬停不会折叠分组、
AI 等待落子期间不重开搜索、滑块只有按住才跟随鼠标、窗口尺寸不超出屏幕。

---

## 版本管理

项目已用 git 管理（`.venv/`、`config/settings.json`、`.workbuddy/artifacts/` 均已忽略，
`.workbuddy/memory/` 里的项目记忆纳入版本控制）。

```bash
git log --oneline        # 提交历史
git status               # 工作区状态
```

## 一些取舍

- **墙的严格规则**：默认禁止横竖墙在同一锚点交叉成「十」字。
  `QuoridorGame(allow_wall_crossing=True)` 可以放开。
- **斜跳的墙检查**：默认检查起跳棋子到斜向落点那条边是否被墙挡住，
  可用 `QuoridorGame(jump_diag_checks_wall=False)` 关闭。
- **棋盘渲染不做通用化**：墙棋的槽位、围棋的点、国象的格子差异太大，
  强行统一反而难维护，因此只共享侧栏/控件/AI 调度，棋盘由各游戏自带视图实现。
- **AI 用线程而不是进程**：纯 Python 搜索会与主循环争 GIL，但主循环大部分时间在等待，
  实测 60 FPS 稳定。引擎接口只传可序列化数据，将来要换 `multiprocessing` 成本很低。
