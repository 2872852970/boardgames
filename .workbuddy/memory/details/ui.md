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

收纳"调一次就不再碰"的参数（`sidebar.PANEL_GROUPS` = `eval` / `ui`），
侧栏底栏「设置」按钮打开，模态，`Esc` / 点遮罩 / 点 `×` 关。

- 分组标题**可折叠**：`_Group.expanded`，点标题行切换（放在 `_visible_widgets()`
  的筛选里，事件 / 绘制 / 同步全都认它）。箭头用 `render.disclosure_arrow()` ——
  三角形是画的，`▶` 字形在部分中文字体里是缺字（侧栏也改用它了）。
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
