# 细节笔记：分层、扩展点、场景、侧栏

> 本文件是 `.workbuddy/memory/MEMORY.md` 的展开。MEMORY.md 只放"最高频致命坑"，
> 长篇原因与验证过程放这里，避免 MEMORY.md 超过注入上限被截断。

## 分层铁律

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
- `settings/schema.py` import `games.<key>.layouts`（纯数据）不成环，因为 games 只依赖 core。

## 新增一个棋类（扩展点）

1. `games/<key>/`：`State`(不可变 + `zobrist_hash`) / `Move`(`@dataclass(frozen=True, slots=True)`) /
   `Game`(`initial_state`、`legal_moves`、`is_legal`、`apply`、`evaluate`、`rollout_move`)；
   用 `SearchOptions` 在搜索期裁剪组合爆炸的着法。
2. 实现 `ui/board_view.py` 的 `BoardView` 协议（`layout/draw/handle_click/handle_motion/animate/update/is_animating/reset/set_last_move`）。
   可选实现 `hover_hint()` / `hud_hint()` 拿专属提示文案（窗口用 `hasattr` 检测）。
   **视图必须保留 `origin` 与 `cell` 两个属性名** —— `tests/ui/helpers.py:pos_for()` 依赖。
   若没有"放置模式"，**必须**实现 `in_placement_mode() -> False`，否则 `MatchScene` 会当成
   支持放墙模式，右键进模式后按 `V` 调用不存在的 `flip_orientation()` 直接崩。
3. `app.py: register_builtin_views()` 里 `registry.register_view(key, factory)`；
   `core/registry.build_default_registry()` 里 `registry.register(game)`。
4. 侧栏参数加在 `settings/schema.py` 的 `SPECS`，**必须打 `games=(key,)` 标**。
   权重键还要加进 `WEIGHT_KEYS`（那是**字面量 tuple**，忘了加则滑块改了完全无效）。
5. 大厅卡片**零改动** —— 卡片数据来自 `Game` 的 `tagline` / `summary` / `rules` / `icon` ClassVar。
   `icon` 目前支持 `"board" | "drop" | "dots" | "hex"`。

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

## 场景架构（大厅 ↔ 对局）

- `ui/scene.py` 的 `Scene` Protocol：`on_enter` / `on_exit` / `layout` / `handle_event` / `update` / `draw`。
- `GameWindow` **只**是窗口宿主（screen / clock / QUIT / VIDEORESIZE / 设置落盘），其余全下发 scene。
- `MatchScene` 持 session / view / sidebar / view_state / toast；`LobbyScene` 持卡片。
- **转发 property 是保住测试的关键**：`tests/ui/*.py` 有 200+ 处 `window.xxx` 访问，
  Python 属性解析不穿透到 scene，所以 `GameWindow` 暴露 `session` / `view` / `sidebar` /
  `view_state` / `board_area` / `sidebar_rect` / `toast` 与 `_update` / `_draw` /
  `_on_setting` / `_on_action` / `_handle_events` 全部转发给 `match`。
  ⚠️ **没有**转发 `_player_details` / `_hint_text` 这类内部方法，测试要直接走 `window.match.xxx(...)`。
- **`GameWindow(start_scene=...)` 默认必须是 `"match"`**（不是 lobby），这样既有
  `make_window()` 夹具零改动。生产入口 `app.main` 显式传 `start_scene="lobby"`。
  默认反直觉，已在 docstring 注明原因。
- **scene 必须每帧从 `window.screen` 读 surface**，绝不能缓存引用 ——
  `test_layout_fits_a_small_window` 会直接 `set_mode` 换掉窗口表面。
- 回大厅**必须先 `session.cancel_thinking()`**（`MatchScene.on_exit` 做的），
  否则后台 AI 线程继续跑并持有旧局面引用。
- `Esc` 语义是**三级**：退放墙模式 → 回大厅 → （大厅里）退出程序。
  Esc 直接调 `window.running` 的断言要用 `window.running is True` 而不是 `pygame.quit()` 已调。
- `PLACEMENT_MODE_KEY` 定义在 `ui/board_view.py`，`quoridor/view.py` 保留
  `WALL_MODE_KEY = PLACEMENT_MODE_KEY` 同值别名 → 8 个引用它的测试零改动。

## 侧栏按模式 + 按游戏精简 + 数值输入

- `ParamSpec` 有 `needs_ai` / `needs_engine`（按引擎过滤）+ **`games`（按棋类过滤）**
  三个可见性条件；`Sidebar` 从 `status.player_types` 解析"实际参战引擎集合"，
  从构造参数 `game_key` 解析当前棋类，据此过滤分组与单个参数。
  **新增参数时务必标好 `games=`，否则会在别的棋类侧栏里露出来。**
- `ParamSpec.choice_labels` 给 choice 型参数提供"值 → 中文标签"的映射
  （`Sidebar._make_widget` 里 `if labels is None and spec.choice_labels: labels = dict(...)`）。
- **双方信息固定在头部**（`PLAYERS_Y`），不参与滚动 —— 侧栏滚动区只放参数。
- **玩家行详情泛化**：`Status.player_details` 只放**数值部分**（"墙 10" / "已落 12 子" /
  "挤出 0/6"），类型标签由侧栏自己拼上去；留空回退到 `walls_left`。
  ⚠️ `_player_details(state, walls)` 是 **MatchScene 的私有方法**，返回 2 元组字符串，
  新增棋类时忘了加分支就会显示成"墙 0"。
- **侧栏标题/副标题**从 `game.display_name` / `game.tagline` 取（`Sidebar.set_game()`）。
- **数值参数可点击输入**：`Slider.value_box` 是右侧的数值框，点它进入编辑态；
  `Sidebar.handle_key()` 在编辑时**接管所有键盘事件**并返回 True，
  否则 Esc / N / U 会误触发退出、新局、悔棋。
  `Sidebar._editing` 保证同时只有一个在编辑，点其他地方 = 确认。
- 底栏 6 个按钮（最小侧栏 316px 下每格 40px，中文两字 28px 放得下）；
  `Button.draw` 在按钮宽度不足时会降一档字号。`_footer_enabled` 按 `button.key` 分派
  （label 会被改文案，key 才稳定）。
- **`RESTART_KEYS`**：改动需要重开一局的参数键集合（棋盘尺寸、每人墙数、起始布局……），
  忘了加会让"棋盘还是旧布局、着法已经按新布局算"。

## 测试目录的公用件

- UI：`tests/ui/conftest.py` 的 `make_window` 夹具（支持 `game_key=` / `start_scene=` 关键字，
  会从 overrides 里抠出来传给 `GameWindow`）+ `tests/ui/helpers.py`（`press` / `motion` /
  `key_event` / `pos_for` / `find_widget` / `visible_slider`）。驱动事件的写法是
  `pygame.event.post(press(pos))` 然后 `window._handle_events()`（**无参数**）。
- 造局面：`tests/games/connect4/conftest.py:make_at(cols, rows, {(col,row):值})`、
  `tests/games/abalone/aba_helpers.py:make_state({(q,r):值}, out=..., current=...)`。
  按坐标写、其余自动填充 —— 手写棋盘图字符串极易抄错。
- ⚠️ **跨测试目录 import 文件名不能重名**：pytest 把每个测试目录都插进 `sys.path` 且
  没有 `__init__.py`，两个 `helpers.py` 会互相覆盖。所以大力士棋用 `aba_helpers.py`。
- ⚠️ **测试文件名必须匹配 pytest 默认规则** `test_*.py`。既有的
  `tests/games/connect4/c4_test_*.py` 曾因此**从未被自动收集（85 项）**，
  2026-10-03 已重命名为 `test_c4_*.py`（保留 `c4_` 段是为了避免跨目录 basename 重名）。
  新棋类一律用 `test_<key>_<thing>.py`，改完用 `find tests -name "test_*.py" -exec basename {} \; | sort | uniq -d` 验一下没有重名。
