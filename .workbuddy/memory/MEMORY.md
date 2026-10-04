# 项目长期记忆：棋类游戏（boardgames）

可扩展的 Python + Pygame 桌面棋类框架，内置**六个**游戏：
**步步为营（墙棋 / Quoridor）**、**重力四子棋（Connect Four）**、**大力士棋（Abalone）**、
**昆虫棋（Hive，无边界 + 可拖拽画布）**、**点格棋（Dots and Boxes）**、**播棋（Mancala / Kalah）**。

> **本文件只放"最高频致命坑"**（每条一句症状 + 一句话断言）。
> 长篇原因、验证过程、逐棋类细节在 `.workbuddy/memory/details/`：
> `architecture.md`（分层/扩展点/场景/侧栏/测试公用件）、`ai.md`（引擎契约/调参/rollout）、
> `ui.md`（事件/绘制/动画/交互/摄像机/**设置浮层**）、`quoridor.md`、`connect4.md`、
> `abalone.md`、`hive.md`。改哪一块先读对应那一篇。
>
> **对外文档在 `docs/`**：`ARCHITECTURE.md`（架构总览 + 坑清单）、`GAMEPLAY.md`（玩法/界面/操作）、
> `USAGE.md`（CLI/两个开关/离屏截图/测试命令/素材授权）、`ADDING_A_GAME.md`（接新棋类的步骤）。
> README 只留主旨、六个游戏简介、项目结构与文档索引。改了框架契约要同步这几份。

## 运行

**Python 3.10+**（`.python-version` 钉 3.10，uv 自动装）；依赖只有 `pygame-ce`。

```bash
uv sync && uv run boardgames                    # 启动（先进大厅；Windows 直接双击 boardgames.bat）
uv run pytest -m "not slow"                     # 日常跑这个（~27s）
uv run pytest                                   # 全量（901 passed / 16 skipped，~40s）
uv run ruff check src tests scripts             # 必须 All checks passed
uv run boardgames --game hive --mode pvp        # 指定棋类；--mode 见下
uv run boardgames --scene match --offscreen --frames 5 --screenshot out/x.png
uv run boardgames --frameless                   # 无边框（≠ --offscreen，见坑 11）
uv run boardgames --hover wall-h --scene match  # 模拟悬停截图（hive-place / dots-edge / mancala-pit…）
uv run boardgames --window 1000x640             # 强制窗口尺寸查布局
PYTHONUTF8=1 uv run python out/verify_v3.py      # 6 棋类 × 3 模式 × 2 尺寸的布局不变量自检
```

- **⚠️ 双击 `boardgames.bat` 报 `No module named 'boardgames'` = 中文路径踩坑**（不是代码 bug）：
  项目在含中文的路径下，uv 的 editable 安装往 `.pth` 写的是 **UTF-8** 的 `...\src`，
  而 `site.py` 在 Windows 上按**系统 ANSI（GBK）**读 `.pth` → 乱码路径 → 静默忽略 →
  `src` 不在 `sys.path`。**解法 `PYTHONUTF8=1`**（bat 里已内置 + `PYTHONPATH` 兜底，别删）。
- **`boardgames.bat` 存成 UTF-8 但正文纯 ASCII，且不要写 `chcp 65001`**（用户明确要求：
  禁用 ConPTY 的终端里会挂 5 分钟；cmd 用系统代码页解 `.bat`，非 ASCII 必乱码）。
- **别每次小改动都跑全量**（用户明确要求）。`tests/conftest.py` 按路径给耗时用例打 `slow`
  （`tests/ai/` 的搜索契约 + 所有 `*rollout*` 整局模拟）；只有改了规则 / 评估 / AI 引擎才跑全量。
- **截图/检查脚本放 `out/`**（已 gitignore）；昆虫棋截图**要加 `--mode pvp`**，
  否则落点提示挂在 `interactive` 上、默认配置拍到"一个落点都没有"的画面。
- **版本红线 3.10**：`dataclass(slots=True)` / `zip(strict=)` / `X | Y` 随便用；
  **PEP 695 泛型 `class Game[S, M]` 要 3.12，不许用**（`core/game.py` 用 `TypeVar` + `Generic`）。

版本控制：`master` 分支；`.venv/`、`config/settings.json`、`out/`、`.workbuddy/artifacts/`、
`.workbuddy/tmp/` 忽略；**`.workbuddy/memory/` 入库**。

## 分层铁律

| 层 | 允许依赖 | 禁止 |
|---|---|---|
| `core/` | 仅标准库 | import pygame、import 具体棋类 |
| `games/<key>/` | core、自己的 geometry | import ai、import ui.sidebar/window（`view.py` 除外） |
| `ai/` | `core.Game` 接口 | import pygame、知道具体棋类 |
| `ui/` | pygame、settings、`board_view` 协议 | 实现规则（**也不 import `games`**） |
| `controller/` | 全部（串联） | 直接绘制 |

- **状态一律不可变**：`Game.apply` 必须返回新对象（悔棋 / AI 搜索 / 多线程读取都靠它）。
- **AI 线程绝不触碰 pygame**，只通过 `AIWorker.poll()` 交回主循环。
- 搜索状态放"每次搜索一个实例"的上下文（`_MinimaxRun` / `_MCTSRun`），引擎对象本身无状态。
- **给框架加能力 = 加 `hasattr` 探测的可选钩子**（摄像机、`clear_hover` / `idle_hint` /
  `pov_player` 都是这么加的）—— 加钩子时其它棋类一行都不用改。

## 跨棋类通用致命坑

1. **`State.winner()` 返回玩家索引 0/1，不是棋子值 1/2**；缓存字段只能叫 `winner_player`。
2. **调色板索引一律玩家号 0/1**（`theme.PLAYER_COLORS` 只有 2 项），写成棋子值会 `IndexError`。
3. **`include_walls` / `include_special` 是墙棋专用，其它棋类必须忽略**；
   `max_branch` 是"从列表头部截断"，所以**截断必须隐含排序**（MCTS 传 `order=False`）。
4. **渲染类 bug 用断言数据结构的测试抓不到** —— 必须"画一帧再取像素"；坐标翻转只在一处做。
5. **新增侧栏参数必须标 `games=(key,)`**；权重键要进 `WEIGHT_KEYS`（字面量 tuple，
   忘了加则滑块完全无效）；要重开一局的键进 `RESTART_KEYS`。
6. **动画拿到的是"走完之后"的局面**（先 `view.animate(move)` 再 `session.play(move)`），
   所以 Move 里给视图的信息必须是**目标格语义**。
7. **`is_terminal()` 要覆盖"该方无处可走"**（昆虫棋显式生成 `PassMove`），否则 MCTS rollout
   空转到抛错、`AIWorker._run` 吞掉异常 → "AI 突然不下棋了"；它本身必须 **O(1)**。
8. **叠层棋类（昆虫棋）的"一格"是 `tuple`**：能动/能选的永远是**栈顶**，
   判定统一走 `owner_at()`，别单独特判甲虫。
9. **摄像机自动适配三条铁律**：① 鼠标按着一帧都不许碰（否则点击被静默吞掉，
   表现是"开局要先滚一下滚轮才能落子"）；② 内容还在视口里就别动；③ `AUTO_FIT_MAX_SCALE = 1.0`
   **只缩不放**。
10. **侧栏"虚拟控件"不在 `SPECS` 里就别问 `settings.get()`**：`pve_side` / `pve_ai` 只是
    `p1_type` / `p2_type` 的另一种说法，`sync_from_settings()` 必须显式跳过它们（否则 KeyError）。
11. **"无边框"和"不显示窗口"是两个开关**：`--frameless`（`NOFRAME` + 自绘标题栏
    `ui/chrome.py`，照常能玩）vs `--offscreen`（dummy 驱动，给 CI）。合并的后果是
    "想去掉标题栏的人得到一个看不见的窗口"。无边框下场景必须用 `window.content_rect`；
    `TitleBar.handle_event` 只吃自己那一条里的事件；`self.titlebar` 必须在开窗口**之前**置好。
12. **`Game` 上的 UI 元数据一律 `getattr` 取**（`goal` / `summary` / `rules` / `howto` / `tips`
    / `tagline` / `display_name` 都是可选 ClassVar），缺一个要降级显示而不是崩。
13. **大厅卡片只放"图标 + 名称 + 副标题 + 一行简介"**，完整规则进 `ui/rules_panel.py` 浮层；
    图标是**局面切片**不是抽象网格（像素级回归在 `test_lobby.py` 的两个 icon 用例）。
14. **场景的 `layout(area)` 必须用传进来的 `area.x / area.y`**，不许写死 0 —— 无边框下
    标题栏最后画，从 y=0 铺开会把侧栏顶部压掉一条（`test_chrome.py` 锁着）。
15. **侧栏只放常用项；引擎参数 / 评估权重 / 界面与操作在 `ui/settings_panel.py`**（详见 `details/ui.md`）：
    - `PANEL_GROUPS` = `minimax` / `mcts` / `eval` / `ui`；侧栏只剩 `game` + `players`；
      控件工厂是模块级 `sidebar.build_widget()`（两边共用）；浮层 `show()` 之后**必须重排**；
    - 浮层**两列**（贪心按列高平衡），`_assign_columns()` → `_content_height()` → `_fit_card()`
      顺序不能乱；两列共用一个 `scroll`；**卡片尺寸恒定**（折叠只改 `max_scroll`）；
    - 浮层里的数值框也能键入：KEYDOWN 必须先给 `_editing`（否则 Esc 直接关浮层）；
    - **每项都有 ↺ 恢复初始值**（`ValueWidget(default=, on_reset=)`）：控件 `handle_event` 必须先调
      `handle_reset()`，右端元素让出 `RESET_W`，`reset()` 后要 `set_value_silently(default)`
      同步自身；↺ 图标用画的（`draw.arc` 方向是反的）；「全部恢复默认」只重置可见项；
    - **凡是"按状态出现"的文本一律预留槽位**（`MODE_HINT_Y` 模式提示行、玩家卡片数字、
      AI 状态行）：只换文案不换高度，否则状态一变整块设置区就跳。
15b. **玩家类型是"能存住 `human` 的 choice"**：界面候选只有 3 种 AI（`choices=AI_TYPES`），
    但 `accepts=PLAYER_TYPES` 让 `"human"` 也能落盘。少了 `accepts`，`coerce` 会静默改写成
    默认值 → 选「我执 玩家 2」无效、下拉显示与实际 AI 不符。**新增 choice 参数时区分"候选"与"允许值"。**
15c. **三种模式和棋局设置一样只在开局前可选**（`enabled = not status.started`），锁定时压蒙版；
    先手固定玩家 1（`first_player` 参数已从设置里删除，规则层构造器参数保留）。
15d. **"我"是哪一方 = `ViewState.pov_player`**（`pve` = 人类那一方，双人 / 自对弈 = `None`
    = 跟随当前行动方；`match_scene._pov_player()` 写入）。昆虫棋靠它把手牌条钉在自己这边。
16. **"对局已开始"不能用 `bool(session.history)`**（`history[0]` 是初始快照，永远非空）——
    正确的是 `session.can_undo()` 或 `is_over`；`game` 组据此锁定。
17. **新游戏一律回到「双人对战」**：复位在 `GameWindow.goto_match()`（从大厅进来 / 换棋类），
    **不是** `MatchScene.__init__`，否则 CLI `--mode eve` 与测试夹具会被悄悄改掉。
18. **`MatchScene` 的三个模态浮层**（顺序即优先级）：`_confirm` → `rules` → `settings_panel`，
    都在 `handle_event` 最前面拦一刀；二级确认只拦「新局 / 大厅」，空棋盘与已终局直接执行。
19. **落子动画没播完 AI 不许动手**（`MatchScene.update`）：`start_thinking()` 要看
    `not view.is_animating()`，**且动画期间不调 `session.poll()`**（着法留在 `_pending_move`，
    `is_thinking()` 仍为真所以状态栏不闪）。视图的 `animate` **不排队**，少挡一处就是
    "我的子被从半空瞬移到落点 + 对面已下完"。
20. **收起的分组要把控件挪出画面**（`visible=False` + `layout(Rect(0,-9000,0,0))`）；
    折叠状态只存实例、别放模块级（会让测试互相污染）；折叠箭头用 `render.disclosure_arrow()`。
21. **有"额外回合"的棋类（点格棋封格、播棋落己方仓库）minimax 已自动支持**：
    检测 `child.current_player == player` 时不取反、alpha/beta 不换边。规则层只要保证
    `apply` 后 `current` 正确即可；MCTS 天然不受影响。
22. **平局终局要跟"未终局"区分**：给 State 加 `over` 字段，`is_terminal` 判 `over`、
    `winner()` 仍返回 `winner_player`；否则平局局面继续生成着法（着法表空）→ MCTS 崩。
23. **像素 → 着法 的换算要做成"最近邻分区"，别留死区**（点格棋踩过）：完整 Voronoi 划分
    + 未落子处画**浅色格线轨道**，缺一半就表现成"鼠标和亮出来的线差半格"。
    取整用 `math.floor(v + 0.5)`（`round()` 是银行家舍入，扫过边界会跳）；
    **命中后造着法必须用 `state.current`**（写死 `player=0` 会让"轮到玩家 2"时预览永远不亮）；
    鼠标离开棋盘要调可选钩子 `clear_hover()`。详见 `details/ui.md`。

## 昆虫棋独有（详见 `details/hive.md`）

- **棋子只有玩家色**（试过掺虫种色 → "最抢眼的变成虫种色、敌我靠推理"）；虫种交给
  **剪影 + 悬停浮窗 + 手牌卡片底边**。改配色先跑 `tests/ui/test_hive_view.py`。
- **`hover_popup` 单层也要弹**（它是虫种的主要出口）；`stack_at` 自下而上，翻转后
  **下标 0 才是顶上那一枚**。
- **无边界**：状态是 `Pos -> 栈`，手牌由"配额 − 盘上数量"**推导**；`zobrist_hash` 必须先做
  **平移归一化**（否则置换表与 MCTS 节点复用全废）。
- **鼠妇搬运时 `dest == src`**：去重要用 `(dest, carried, carried_dest)` 复合键。
- **`pixel_to_axial` 用 half-up**（`math.floor(v + 0.5)`），`round()` 会让边界格乱跳。
- **MCTS 只有 ~83 nps**（六个棋类里最慢），优先 Minimax（d4~6、候选 16~32）。
- **人机对战手牌条钉在我方**（`_hand_player(view)` = `view.pov_player`），
  `pov != state.current` 时清掉残留选择 / 落点表并拒绝点击 —— 否则轮到 AI 时手牌条整块切到
  对手那边，等于免费看对手的牌。
