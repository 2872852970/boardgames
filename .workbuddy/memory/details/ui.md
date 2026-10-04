# 细节笔记：UI 层（事件、绘制、动画、棋盘交互）

## 事件循环

- **事件处理必须判断 `event.type`**。曾出现"分组标题折叠"对**任何**事件都翻转 `expanded`，
  鼠标一划过就每帧翻一次，连标题下的下拉菜单一起疯狂抖动。折叠/按钮之类的交互
  一律限定 `MOUSEBUTTONDOWN + button == 1`。
- **`MOUSEBUTTONUP` 必须无条件派发给控件**。只在鼠标位于侧栏内时才派发，会让
  "在侧栏外松开左键"的滑块永远停在拖拽态，之后不按键鼠标一动就改数值。
  滑块自身还要在 `update()` 里用 `pygame.mouse.get_pressed()` 兜底解除。
- **`Session.is_thinking()` 必须包含 `_pending_move`**。AI 结果已返回但落子停顿（`ai_delay_ms`）
  还没过完时若返回 False，主循环每帧都会重开搜索 → "思考中"闪烁且 AI 永远不落子。
  这类 bug 只在 `ai_delay_ms > AI 思考耗时` 时暴露，测试里用大 `ai_delay_ms` 才能覆盖。

## 窗口与布局

- **窗口尺寸必须裁剪到屏幕**（`ui.window.choose_window_size()`），否则小屏 / 高 DPI 下
  底部按钮会被裁掉。侧栏宽度也随窗口自适应（`SIDEBAR_W` → `SIDEBAR_MIN_W`，
  最小值 316px）。
- **场景布局必须用传进来的 `area.x / area.y`**，不要写死 `0`。无边框窗口把
  `content_rect`（顶部让出 `TITLEBAR_H = 34`）传给场景，而标题栏是**最后**画的；
  场景若从 y=0 开始铺，侧栏顶部的游戏名 / 模式切换会被标题栏压掉一条
  （`MatchScene.layout` 曾踩过，现由 `tests/ui/test_chrome.py::
  test_match_scene_also_stays_below_the_title_bar` 守着）。
- 中文字体按**文件路径**加载并缓存。缺字陷阱：`▾/▸` 和 `▶`（U+25B6）在微软雅黑里没有，
  别用字形画箭头 —— 用 `pygame.draw.polygon` 画。`▼/▲` 是有的。
- 面板类绘制顺序：内容 → 覆盖层（下拉弹层）最后画，并 `set_clip` 到面板矩形。
- **棋盘左上角的提示胶囊宽度是自适应文字的**（`match_scene` 里 `font.size(label)[0] + 26`，
  下限 210px、上限 `area.width - 36`）。旧的固定 210px 会把长提示从两侧截掉，
  看着像"文字跑到屏幕外面去了"。**新棋类的 `hover_hint` 文案尽量 ≤ 20 汉字**。

## 侧栏结构（`ui/sidebar.py`）

- 头部固定（`HEADER_H = 196`，不滚动）：游戏名 + **右侧那行状态**（轮到谁 / 思考中 /
  结果）+ 副标题 + 模式分段控件 + **两张玩家卡片**（`_players_rect`：颜色点、身份标签、
  当前棋类的进度数字；轮到谁谁加玩家色描边 + 左侧色条）。
  进度数字由窗口的 `_player_details()` 按棋类提供。
- 底栏两行（`FOOTER_H = 108`）：`_footer_rows = (("new_game","undo"), ("pause","step","lobby","settings"))`，
  按 `visible` 里的 key 铺满整行；「新局」在等宽基础上再乘 1.25 的权重。
  `_layout_footer()` 在 `layout()` 与 `_draw_footer()` 里各调一次
  （后者是为了让命中区跟绘制同步）。
- 滚动区只剩 `game` + 玩家状态行 + `players`，`_flow()` 仍保证 `game` 排第一。
- 左上角提示胶囊的空闲文案：**轮不到你时先显示 `_blocked_reason()`**（"AI 正在思考…" /
  "动画播放中…" / "已暂停…"），只有能动手时才走视图的可选钩子 `idle_hint()`；
  没有钩子的棋类给「选择落点」（**不要**再用"投子" —— 那是四子棋的词）。
- **模式分段控件也只在开局前可选**（`_mode_widget.enabled = not status.started`），
  锁定时压一层 `(*BG_ALT, 150)` 蒙版。模式下方 `MODE_HINT_Y = 97` 处**常驻一行 16px 提示**
  （未开局"三种模式在对局开始后锁定" / 已开局"已开始 · 开新局可改"）——
  常驻是因为"按状态出现"的文本会让下面的玩家卡片跟着跳。
  改头部高度记得同步 `HEADER_H`（现在 226，取值为"玩家卡片底 + 分隔线"）。
- **"我"是哪一方 = `ViewState.pov_player`**（可选字段，`match_scene._pov_player()` 写入：
  `pve` = 人类那一方，双人 / 自对弈 = `None` 表示跟随当前行动方）。
  昆虫棋用它把手牌条钉在自己这边（见 `hive.md`）。

## AI 自对弈的暂停与单步

- `GameSession.new_game()` 在 `mode == "eve"` 时 `paused = True`；
  `ai_allowed()` 决定 AI 能不能动（`not paused or stepping`），
  `start_thinking()` 用它做闸门 —— 所以窗口可以直接无条件调用。
- `request_step()` 置 `stepping = True`；`poll()` 落子后把 `stepping` 复位，`paused` 不变，
  因此单步走完仍然暂停。侧栏在 eve 模式才显示「单步」「暂停」两个按钮。

## AI 调度必须让开落子动画（`MatchScene.update`）

上一手的落子动画没播完，AI 不许动手。各视图的 `animate` 刻意**不排队**
（新动画顶掉旧的），所以少挡一处就会出现"玩家那一枚被从半空瞬移到落点 +
对面已经下完"，也就是"我的子还没落地 AI 就落子了"。

```python
animating = self.view.is_animating()
if not session.is_over and session.is_ai_turn() and not animating:
    session.start_thinking()          # ① 动画期间不起搜索
move = None if animating else session.poll()   # ② 动画期间不取结果
if move is not None:
    self._play_move(move)
```

- **两处都要挡**：只挡 ① 挡不住自对弈"点棋盘单步"（搜索是上一次起好的，结果照样被取走）；
  只挡 ② 则 AI "白想"一段时间、状态栏一直显示思考中。
- ② 期间着法留在 `session._pending_move` 里，`is_thinking()` 仍为真 → 状态栏不闪，
  动画结束的下一帧就落子。
- 自对弈单步同理：动画没播完时 toast 说「排队：上一手落完就走」，别报假的"思考中"。

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
- `duration_ms == 0` → 不播放（沿用 `QuoridorView` 的约定，大力士棋也照此）。
- 四子棋的落差由 `Connect4View.drop_px_for(row)` 给：**所有棋子从棋盘上沿之上
  `DROP_ENTRY_CELLS` 格进场，落点越低掉得越远**（真棋具就是从顶口投子）。
  别用固定落差 —— 翻转坐标后固定落差会让棋子"在棋盘中间凭空出现"。

## 「设置」浮层（`ui/settings_panel.py`）

收纳"调一次就不再碰"的参数（`sidebar.PANEL_GROUPS` = `minimax` / `mcts` / `eval` / `ui`；
侧栏只剩 `game` + `players`），侧栏底栏「设置」按钮打开，模态，`Esc` / 点遮罩 / 点 `×` 关。

- **按引擎过滤**：引擎参数都标了 `needs_engine`，浮层按 `player_types` 只列**实际参战**
  的那一套（双人对战里全不显示）。所以 `show(game_key, player_types)` 拿到的是
  `session.resolved_player_types()`。
- **两列排布**：`_assign_columns()` 按"放进当前较矮的那列"贪心分组，再
  `_content_height()`（取两列最高）→ `_fit_card()`。顺序不能反 —— 卡片高度依赖列归属。
  两列共用一个 `scroll` 与一个滚动条。
- **数值框可键入**：`handle_event` 里 KEYDOWN 必须先交给 `self._editing`，
  否则 Esc 会把浮层关掉、数字根本打不进去（点别处 = 确认并结束输入）。
- **展开的下拉要最后画**：`_open_dropdowns()` 在事件里优先接管、在绘制里
  `draw_overlay()` 收尾（当前分组里只有开关 / 滑块，留个兜底）。
- **卡片尺寸恒定**：`_fit_card()` 只由可用区域决定（`max(260, min(CARD_MAX_H, area.height-48))`），
  **不再跟着内容缩** —— 折叠一个分组就让卡片、关闭按钮、两列位置全跳一下，观感比"底部留白"糟得多。
  折叠 / 展开只改 `max_scroll` 与两列的重新分配。
- 分组标题**可折叠**：`_Group.expanded`，点标题行切换（放在 `_visible_widgets()`
  的筛选里，事件 / 绘制 / 同步全都认它）。箭头用 `render.disclosure_arrow()` ——
  三角形是画的，`▶` 字形在部分中文字体里是缺字（侧栏也改用它了）。
- **「恢复初始值」**（侧栏与浮层共用，实现在 `widgets/base.py` 的 `ValueWidget`）：
  `default` + `on_reset` → 行右侧长出 ↺，`has_reset`（值 ≠ 默认）才亮。四个坑：
  ① 各控件 `handle_event` **必须先调 `handle_reset()`**（滑块的拖拽区盖住整行）；
  ② 右端元素（`value_box` / `_switch` / `_box`）都要让出 `RESET_W = 26`，与 `has_reset`
     无关，否则 ↺ 一亮同行元素就左右跳；
  ③ `reset()` 走完 `on_reset()` 还要 `set_value_silently(default)` 同步自身（`on_reset`
     只负责写回设置），否则"设置里是 4、界面还写 7、↺ 还亮着"；
  ④ ↺ 图标**别用 `pygame.draw.arc`**（角度与视觉方向相反，只画出半个圈像乱码），
     改成采样折线 + 端点切线箭头（同 `disclosure_arrow` 为什么是画的）。
  浮层右上角「全部恢复默认」只重置 `_widget_applicable` 的项，点完立刻刷新按钮状态。
- 收起的分组要把控件 `visible=False` **且** `layout(Rect(0, -9000, 0, 0))` 挪出画面：
  只标不可见的话它们还在原坐标上接事件（点空白处会改到看不见的滑块）。
- 折叠状态**只存实例上**，不要放模块级：模块级会让"某个测试先折叠了 eval"
  污染别的测试的可见键断言，变成顺序相关的偶发失败。
- 卡片高度跟着内容走（`_fit_card`，上限 `CARD_MAX_H`）：整组收起后卡片要跟着缩，
  否则底下留一大片空白，看着像加载失败。
- `sync_from_settings()` 同步**全部**控件（不只是可见的），这样折叠中的分组
  展开时显示的是当前值而不是"上次打开时的旧值"。

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

## 棋盘交互约定（Connect Four / 大力士棋）
- 四子棋：鼠标移到某一列就预览落点，点击投子。
- 大力士棋：**两段式点击**（点棋子选组 → 点目标格出招），不做拖拽。
  详见 `abalone.md`。

## 棋盘交互约定（点格棋）——"鼠标和线差半格"是怎么根治的

`games/dotsboxes/view.py` 的 `_edge_at` 把整块棋盘按"离哪条边最近"切成 Voronoi：

- 候选只取两条：**最近的水平边**（行 = `_half_up(gy)` 夹紧，列 = `floor(gx)` 夹紧）
  与**最近的垂直边**（列 = `_half_up(gx)`，行 = `floor(gy)`）—— 水平边的垂直距离
  只跟行有关、沿边距离只跟列有关，所以两边各自取最近就是全局最近，不必枚举全部边。
- 距离是**到线段的欧氏距离**（`_segment_distance`：垂直偏离 + 沿边夹紧后的偏离），
  取小的那条；一样近取水平边，保证交点处结果确定。
- 棋盘内**处处**能命中（含棋盘外半格余量）→ 没有死区。旧写法是"`round` 取整 +
  ±0.42 格的窄带"，格心点不动任何东西，玩家就会看到"指着线，亮的是旁边那条"。
- 未画的边画成**浅色格线轨道**（`_draw_slots`，受 `show_hints` 控制）：
  高亮落在哪条线上不用猜。画序：格 → 轨道 → 已画的边 → 幽灵 → 点。
- `_edge_at` 只返回 `(orient, row, col)`，**着法一律由调用方用 `state.current` 造**
  —— `is_legal` 会校验 `move.player == state.current`，命中函数里塞个写死的
  `player=0` 会让"轮到玩家 2"时预览永远不亮（真踩过）。
- 鼠标离开棋盘由场景调可选钩子 `clear_hover()`（`hasattr` 探测），
  否则幽灵线会一直挂在画面上。
- `idle_hint()` 给左上角胶囊一句"移到两点之间的格线上"；不实现就会落到
  通用兜底文案（以前是四子棋的"投子"）。

## 摄像机（`ui/camera.py`）——无边界棋盘的通用能力

只有昆虫棋在用，但实现在框架层，**另外三个棋类一行未改**。

- 变换：`screen = world * scale + offset`，`offset` = 世界原点的屏幕位置。
  `set_viewport()` 换视口时保持画面不动；`zoom_at()` 以光标下的世界点为锚点。
- **`fit(rect, padding, max_scale)` 的 `max_scale` 是软上限**：开局内容包围盒很小，
  不设上限会把一枚棋放大到铺满画布（视觉 bug，不是数学 bug）。树里传 `1.06`。
- **点击 vs 拖拽必须由 `CameraController` 裁决**：按下 → 扣住 → 松手时按**累计位移**
  判（`DRAG_SLOP = 4`px）。返回 `NONE / CONSUME / CLICK`；`CONSUME` 直接 return，
  `CLICK` 才转成棋盘点击。少了它，"手抖一下"就会平移画布之后误落子。
  中键拖动永不产生点击；鼠标在视口外按下/滚轮一律忽略。
- `MOUSEWHEEL` 事件在测试里可能不带 `pos` → 用
  `getattr(event, "pos", None) or pygame.mouse.get_pos()`（否则会缩放到屏幕左上角）。
- `buttons` 全 0 时兜底 cancel（切窗口回来会丢 MOUSEBUTTONUP）。
- 视图侧**全部是可选的 `hasattr` 钩子**：`camera` / `camera_viewport()` /
  `auto_fit_camera(state)` / `hud_inset()` / `idle_hint()` / `world_bounds(state)`。
  加钩子不影响老棋类，这是"给框架加能力"而不是"给三个棋类改代码"的关键。
- `auto_fit` 的节奏：开局 / 重开一局 / 悔棋时置 `True`（每帧把内容塞进视口），
  玩家一滚轮或一拖拽就置 `False` 再也不抢镜头；只有按 `F` 才收回。
