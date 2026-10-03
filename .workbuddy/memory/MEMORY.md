# 项目长期记忆：棋类游戏（boardgames）

可扩展的 Python + Pygame 桌面棋类框架，已内置**四个**游戏：
**步步为营（墙棋 / Quoridor）**、**重力四子棋（Connect Four）**、**大力士棋（Abalone）**、
**昆虫棋（Hive，无边界棋盘 + 可拖拽画布）**。

> **本文件只放"最高频致命坑"。** 长篇原因、验证过程、逐棋类细节在
> `.workbuddy/memory/details/`：`architecture.md`（分层/扩展点/场景/侧栏/测试公用件）、
> `ai.md`（引擎契约/调参/rollout）、`ui.md`（事件/绘制/动画/交互/**摄像机**）、
> `quoridor.md`、`connect4.md`、`abalone.md`、`hive.md`。改哪一块就先读对应那一篇。
>
> **对外文档在 `docs/`**（README 精简后长文都挪到了这里）：
> `docs/ARCHITECTURE.md`（项目总结 / 架构总览 / 跨棋类坑清单）、
> `docs/GAMEPLAY.md`（玩法 / 界面 / 操作 / 快捷键 / AI）、
> `docs/USAGE.md`（CLI 参数 / 两个开关 / 离屏截图 / 测试命令 / 素材授权）、
> `docs/ADDING_A_GAME.md`（新增棋类的实操步骤与代码模板）。
> README 只留：如何运行（双击 `boardgames.bat`）、主旨、四个游戏简介、项目结构、文档索引。
> 改了框架契约或扩展点，ARCHITECTURE / ADDING_A_GAME 要同步更新。

## 运行

**Python 3.10+**（`.python-version` 钉住 3.10，uv 自动装）。依赖只有 `pygame-ce`。

```bash
uv sync && uv run boardgames            # 启动（先进大厅）
uv run pytest -m "not slow"             # 快的（几秒）—— 日常改动跑这个
uv run pytest                           # 全量（804 passed / 11 skipped，约 40s）
uv run ruff check src tests scripts     # 必须 All checks passed
uv run boardgames --game hive           # 也可 --game connect4 / abalone / quoridor
uv run boardgames --scene match --offscreen --frames 5 --screenshot out.png  # 离屏（无窗口）
uv run boardgames --frameless                                               # 无边框（= 无系统标题栏）
uv run boardgames --hover wall-h --scene match   # 模拟悬停（大力士棋 --hover aba-select、
                                                 # 昆虫棋 --hover hive-place / hive-select）
uv run boardgames --window 1000x640     # 强制窗口尺寸调试布局
```

**⚠️ 双击 `boardgames.bat` 报 `No module named 'boardgames'` = 中文路径踩坑**（不是代码 bug）：
项目在 `C:\Users\Admin\WorkBuddy\棋类游戏` 这种**含中文**的路径下，uv 的 editable 安装
往 `.venv\Lib\site-packages\_editable_impl_boardgames.pth` 写的是 **UTF-8** 的 `...\src`，
而 Python 的 `site.py` 在 Windows 上按**系统 ANSI 编码（GBK/936）**读 `.pth` → 解出乱码路径
→ 目录不存在 → 被静默忽略 → `src` 不在 `sys.path`。
**解法：设 `PYTHONUTF8=1`**（PEP 540，`.pth` 改按 UTF-8 读）。git bash 下 locale 不同所以
能跑，cmd.exe（双击）必挂 —— 这正是"bash 里好好的、双击就起不来"的原因。
`boardgames.bat` 里已写好 `PYTHONUTF8=1` + `PYTHONPATH` 双保险，别删这两行。

**`boardgames.bat` 的编码约定**（用户明确要求）：存成 **UTF-8，但正文保持纯 ASCII**，
**不要写 `chcp 65001`**（实测在禁用 ConPTY 的终端里会挂起 5 分钟以上；且 cmd 用系统
代码页解 `.bat`，非 ASCII 字节一律变乱码）。中文说明放 README / `docs/USAGE.md`。
`.gitattributes` 里钉了 `*.bat text eol=crlf`。

**昆虫棋截图必须加 `--mode pvp`**：落点提示挂在 `interactive` 上，`config/settings.json`
里若存了 `mode=eve`，默认命令会拍到"一个落点都没有"的画面。

**别每次小改动都跑全量测试**（用户明确要求）。`tests/conftest.py` 按路径给耗时用例打
`slow`（`tests/ai/` 的搜索契约 + 所有 `*rollout*` 整局模拟），日常用 `-m "not slow"`；
只有改了**规则 / 评估函数 / AI 引擎**才跑全量。

**版本红线（最低 3.10）**：`dataclass(slots=True)`、`zip(strict=)`、`X | Y` 运行时联合
都是 3.10 才有，随便用；**PEP 695 泛型 `class Game[S, M]` 要 3.12，不许用** ——
`core/game.py` 用的是 `TypeVar` + `Generic`。（曾一路降到 3.7 试过，PEP 585 / 695 /
slots / Protocol / Literal / dict `|` 全都要兜底，最后定在 3.10。）

git 分支 `master`。`.venv/`、`config/settings.json`、`.workbuddy/artifacts/`、
`.workbuddy/tmp/` 已忽略；
`.workbuddy/memory/` 纳入版本控制。

## 分层铁律

| 层 | 允许依赖 | 禁止 |
|---|---|---|
| `core/` | 仅标准库 | import pygame、import 具体游戏 |
| `games/<key>/` | core、自己的 geometry | import ai、import ui.sidebar/window（`view.py` 除外） |
| `ai/` | `core.Game` 接口 | import pygame、知道具体棋类细节 |
| `ui/` | pygame、settings、board_view 协议 | 实现规则（**也不 import `games`**） |
| `controller/` | 全部（串联） | 直接绘制 |

- **状态一律不可变**：`Game.apply` 必须返回新对象（悔棋 / AI 搜索 / 多线程读取都靠它）。
- **AI 线程绝不触碰 pygame**，只通过 `AIWorker.poll()` 交回主循环。
- 搜索状态放在"每次搜索一个实例"的上下文（`_MinimaxRun` / `_MCTSRun`），引擎对象本身无状态。
- **想给框架加能力，就用 `hasattr` 探测的可选钩子**（摄像机就是这么加的）——
  加钩子时另外三个棋类一行都不用改。

## 跨棋类通用致命坑

1. **`State.winner()` 返回玩家索引 0/1，不是棋子值 1/2**；缓存胜者的字段只能叫
   `winner_player`（叫 `winner` 会遮蔽 ABC 方法）。
2. **调色板索引一律玩家号 0/1**（`theme.PLAYER_COLORS` 只有 2 项）。写成"棋子值"会让
   玩家 2 的悬停/赢棋高亮直接 `IndexError`。
3. **`include_walls` / `include_special` 是墙棋专用，其他棋类必须忽略**；
   而 `max_branch` 是"从列表头部截断"，所以**截断必须隐含排序**（MCTS 传 `order=False`）。
4. **渲染类 bug 用断言数据结构的测试永远抓不到** —— 必须"画一帧再取像素"
   （`surface.get_at(...)`）；坐标翻转只允许在一处做。
5. **新增侧栏参数必须标 `games=(key,)`**；权重键还要加进 `WEIGHT_KEYS`
   （字面量 tuple，忘了加则滑块改了完全无效）。需要重开一局的键要进 `RESTART_KEYS`。
6. **播放动画拿到的永远是"走完之后"的局面**（先 `view.animate(move)` 再 `session.play(move)`），
   所以 Move 里给视图用的目标格信息必须是**目标格语义**，不能给源格。
7. **`is_terminal()` 要覆盖"该方无处可走"**：要么像昆虫棋那样**显式生成 `PassMove`**，
   否则 MCTS 的 rollout 会空转到抛错，表现为"AI 突然不下棋了"（`AIWorker._run` 吞掉了异常）。
   反过来 `is_terminal()` 本身必须 **O(1)**，绝不能在里跑着法生成。
8. **叠层棋类（昆虫棋）的"一格"是 `tuple`**：能动/能选的永远是**栈顶**；
   所有判定走 `owner_at()`（= 栈顶归属），别单独特判甲虫。
9. **摄像机自动适配有三条铁律，一条都不能少**（`MatchScene._auto_fit_camera`）：
   ① 鼠标按着时一帧都不许碰 —— 每帧重算会把同帧刚记下的"按下"清掉，
   **点击被静默吞掉**（表现："开局必须先滚一下滚轮才能落子"）；
   ② 内容还在视口里就别动（先问视图 `world_bounds(state)` 再 `camera.contains`），
   否则每落一子镜头缩一下；
   ③ `AUTO_FIT_MAX_SCALE = 1.0` **只缩不放**，开局超过 100% 就是 bug。
10. **侧栏"虚拟控件"不进 `SPECS` 也就不该问 `settings.get()`**：人机对战的两个
    控件（`pve_side` / `pve_ai`，见 `ui/sidebar.py`）只是 `p1_type` / `p2_type` 的
    另一种说法，`sync_from_settings()` 必须显式跳过它们，否则抛 KeyError。
11. **"无边框"和"不显示窗口"是两个开关，别混**：
    `--frameless`（`GameWindow(frameless=True)`，`pygame.NOFRAME` + 自绘标题栏
    `ui/chrome.py`，窗口照常能玩）才是用户说的"无头（无 pygame 标题头）"；
    `--offscreen`（dummy 驱动）是给 CI / 跑批用的。混成一个的后果是
    "想去掉标题栏的人得到了一个看不见的窗口"。
    - 无边框下场景必须用 `window.content_rect`（顶部让出 `TITLEBAR_H`）；
    - `TitleBar.handle_event` **只吃落在自己那一条里的鼠标事件**，其余放行给场景；
    - `_flags()` 会被 `_open_screen()` 调用，所以 `self.titlebar` 必须在开窗口**之前**置好。
12. **`Game` 上的 UI 元数据一律 `getattr` 取**：`goal` / `summary` / `rules` / `howto` /
    `tips` / `tagline` / `display_name` 都是可选 ClassVar，规则浮层缺一个就该降级显示，
    不能崩。四个棋类都要写全（`tests/ui/test_lobby.py::test_every_game_has_a_readable_rulebook`
    和 `tests/ui/test_rules_panel.py::test_sections_cover_the_whole_rulebook` 锁着）。
13. **大厅卡片只放"图标 + 名称 + 副标题 + 一行简介"**，完整规则进
    `ui/rules_panel.py` 的浮层（大厅与对局共用同一个 `RulesOverlay` 实例持有方式）。
    卡片上的图标是**局面切片**而不是抽象棋盘网格 —— 像素级回归在
    `test_lobby.py::test_connect4_icon_keeps_every_piece_on_the_board`
    （"落点不许画成一枚悬在线盘上方的子"）和 `test_abalone_icon_shows_a_crowd_of_marbles`
    （数独立色块，抓"盘上只剩四枚子"）。
14. **场景的 `layout(area)` 必须用传进来的 `area.x / area.y`，不许写死 0**。无边框窗口
    把 `content_rect`（顶部让出 `TITLEBAR_H = 34`）交给场景，而标题栏是**最后**画的：
    场景若从 y=0 铺开，侧栏顶部的游戏名 / 模式切换会被标题栏压掉一条
    （`MatchScene.layout` 踩过；`tests/ui/test_chrome.py::
    test_match_scene_also_stays_below_the_title_bar` 锁着）。
15. **侧栏只放常用项，「评估权重 / 界面与操作」在 `ui/settings_panel.py`**：
    - 分组的归属由 `sidebar.PANEL_GROUPS` 决定，控件工厂是模块级 `sidebar.build_widget()`
      （侧栏与浮层共用，别再复制一份）；
    - 浮层 `show(game_key, player_types)` 之后**必须重排**（按棋类过滤会改变可见集合）；
    - 侧栏分组断言在 `test_window_smoke.py` / `test_hive_wiring.py` / `test_lobby.py`，
      改分组要一起改。
16. **"对局已开始"不能用 `bool(session.history)`** —— `history[0]` 是**初始快照**，
    永远非空。正确的是 `session.can_undo()`（= `len(history) > 1`）或 `is_over`。
    棋局设置（`game` 组）由此锁定：`widget.enabled = not status.started`，
    并在 `_draw_content` 里压一层底色；标题旁写「已开始 · 开新局可改」。
17. **新游戏一律回到「双人对战」**：复位发生在 `GameWindow.goto_match()`（从大厅进来 /
    换棋类时 `settings.set("mode", "pvp")`），**不是** `MatchScene.__init__` ——
    否则 CLI `--mode eve` 与测试夹具（直接构造窗口）会被悄悄改掉。
18. **`MatchScene` 的三个模态浮层**（顺序即优先级）：`_confirm` → `rules` →
    `settings_panel`，都在 `handle_event` 最前面拦一刀。二级确认只拦「新局 / 大厅」，
    空棋盘与已终局直接执行；结算浮层的 `×` 只置 `_result_dismissed`，`_restart()` 里复位。
19. **落子动画没播完，AI 不许动手**（`MatchScene.update`）：`start_thinking()` 要看
    `not view.is_animating()`，**而且动画期间不调 `session.poll()`**（着法留在
    `_pending_move` 里，`is_thinking()` 仍为真所以状态栏不闪）。视图的 `animate` 是
    **不排队**的（新动画顶掉旧的），少挡一处就是"我的子被从半空瞬移到落点 + 对面已下完"。
20. **收起的分组要把控件挪出画面**（`visible=False` + `layout(Rect(0,-9000,0,0))`）：
    只设不可见，它们还在原坐标接事件。折叠状态只存实例、别放模块级（会让测试互相污染）。
    折叠箭头一律用 `render.disclosure_arrow()`（`▶` 字形在部分中文字体里缺字）。

## 昆虫棋独有（详见 `details/hive.md`）

- **棋子只有玩家色**（`KIND_BODY_BLEND` / `KIND_LINE_BLEND` 恒为 0，描边用 `PLAYER_DARK`）。
  试过掺虫种色，结果"最抢眼的变成虫种色、敌我靠推理"——**敌我识别优先级远高于虫种**。
  虫种交给**剪影 + 悬停浮窗（`hover_popup`）+ 手牌卡片底边**，这三处都不在棋盘上。
  改配色先跑 `tests/ui/test_hive_view.py`（里面有跨玩家/跨虫种色差的量化回归）。
- **`hover_popup` 单层也要弹**（悬停标识就是虫种的主要出口）；单层不画标题
  （`title_h = 0`），多层才列"谁压着谁"。注意 `stack_at` 自下而上，翻转后
  **下标 0 才是顶上那一枚**（`is_top = index == 0`）。
- **无边界**：状态是 `Pos -> 栈` 映射；手牌由"配额 − 盘上数量"**推导**，不单独存。
- **`zobrist_hash` 先做平移归一化**（整体平移到最左下的格在 `(0,0)`），否则置换表与
  MCTS 节点复用全废。
- **鼠妇搬运时 `dest == src`**（它自己不挪窝）→ `destinations()` 只报 `carried_dest`；
  去重要用 `(dest, carried, carried_dest)` 复合键，只按 `dest` 会把八种搬运并成一手。
- **`pixel_to_axial` 用 half-up**（`math.floor(v + 0.5)`），用 Python `round()` 会让边界格乱跳。
- **MCTS 只有 ~83 nps**（四个棋类里最慢），昆虫棋优先用 Minimax（d4~6、候选 16~32）。
