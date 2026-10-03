# 细节笔记：大力士棋（Abalone / 大王鲍）

六边形推挤棋。模块：`src/boardgames/games/abalone/`
（`geometry` / `layouts` / `state` / `move` / `rules` / `heuristic` / `view`）。
`key = "abalone"`，`icon = "hex"`，双方各 14 子，先挤出对手 6 枚者胜。

## 几何（`geometry.py`）

- **pointy-top 六边形 + axial `(q, r)`**；半径 4 = 61 格，合法条件
  `max(|q|, |r|, |q + r|) <= 4`；行 `r ∈ [-4,4]`，行宽 `9 - |r|` = **5,6,7,8,9,8,7,6,5**。
- 六方向（下标即 `AbaloneMove.direction`）：`E(1,0) NE(1,-1) NW(0,-1) W(-1,0) SW(-1,1) SE(0,1)`；
  三条轴 `d % 3`（0=E/W，1=NE/SW，2=NW/SE），`d` 与 `d+3` 反向。
- 像素：`x = size*√3*(q + r/2)`、`y = size*1.5*r`；反解用 cube round，
  **舍入必须 half-up（`math.floor(v+0.5)`）** —— Python 内置 `round()` 是 banker's rounding，
  恰好落在两格分界上的像素会跳到隔壁格子（"这一格点不中"）。
- 预计算表：`CELLS`(61) / `INDEX` / `NEIGHBORS`(61×6，越界 -1) / `LINES`(285) /
  `LINES_INDEX`(285) / `RING` / `CENTER_SCORE` / `BOARD_UNIT_W=9√3` / `BOARD_UNIT_H=14`。
- 参考：<https://www.redblobgames.com/grids/hexagons/>（axial/cube round 的标准做法）。
- 纯标准库，**不 import pygame**。

## 布局（`layouts.py`）

`MARBLES_PER_PLAYER=14`、`WIN_OUT=6`、`ABALONE_SETUPS`、`SETUP_LABELS`、`setup_cells(setup)`。

- 标准布局：双方**中心对称**（`(q,r) -> (-q,-r)`）。
- 两种雏菊：双方**左右镜像**（`(q,r) -> (-q-r, r)`），且每方自身中心对称。
- ⚠️ 标准布局占满两整行，**「整行的左右镜像还是它自己」** —— 所以不能统一用镜像关系
  去测两种布局（`test_side_relations_are_the_documented_ones` 锁的就是这个）。
- 开局合法着法数 **standard 44 / belgian_daisy 52 / german_daisy 80**（测试锁着）。

## 状态（`state.py`）

- `AbaloneState(frozen)`：`cells`(61 长 tuple，0/1/2) / `out` / `current` / `ply` / `winner_player`。
- **`out[p]` = `p` 把对手推出去的子数**（不是"p 自己掉了几个"）。记反了胜负符号整个反掉。
- **缓存胜者的字段叫 `winner_player`，绝不能叫 `winner`**（会遮蔽 ABC 的 `winner()`）。
- `zobrist_hash() = hash((cells, current))`，排除 `out`/`ply`/`winner_player`
  （`out` 可从盘面推出：`out == (14 - 对方盘上子数, 14 - 我方盘上子数)`）。
- **`is_terminal()` 有第二条防御性判据**：行棋方在盘上一枚子都不剩也算终局。
  正常对局（28 枚守恒）轮不到，但没有它 MCTS 的 rollout 会在"非终局且无处可走"的节点上
  一直索取着法直到抛 `RuntimeError`（AI 线程吞异常 → "AI 突然不下棋"）。
  用 `marble_count()`（一次 61 长遍历）实现，**不要**在这里调 `legal_moves`（会让 MCTS 慢一倍）。
  注意它**不**顺手判胜负：`winner()` 仍只看 `winner_player`。

## 着法（`move.py`）

- 身份字段 `player` / `cells`(排序) / `direction`；`pushed` / `ejected` 是
  **`field(compare=False, repr=False)`** —— 视图构造的 Move 必须与 `legal_moves` 产出的相等
  （否则 `is_legal` 判非法），且 MCTS 用 `dict[Move, _Node]` 存子节点。
  非存不可的原因：`MatchScene._play_move()` 是**先** `view.animate(move)` **再** `session.play(move)`。
- **`destinations()` 返回的是目标格、不是源格**。`draw` 拿到的永远是**走完之后**的局面，
  按源格比对等于一个都对不上 → 表现为"棋子瞬移、动画根本没播"（实测踩过）。
  `ejected` 不在其中（它已经不在盘上），视图单独把它从源格朝盘外滑出去并淡出。
- `describe()` 用 `group_axis` 区分「直线」/「横移」（`direction % 3 == group_axis(索引)`）。
- `is_placement` 恒为 `False`（没有放置型着法）。

## 规则（`rules.py`）

- `_plan(cells, group, axis, direction, me)` 一次判定：直线移动（含推挤）或横移。
  - inline：`0 < M < n` 才合法（M = 对手挡路子数，n = 我方组大小），别格必须空；
    推挤后最后一格要么空、要么出界（那个子记进 `ejected`）；
    被推组的**再下一格**必须空或出界；**己方子在后方也算堵住**。
  - broadside：整组每个目标格都必须在盘且为空 —— 所以横移永远不能推。
- `legal_moves`：单子单独扫 6 方向；2/3 连子只从 `LINES_INDEX` 取（避免单子被重复生成三遍）。
  **忽略 `include_walls` / `include_special`**；`order=True` 时按 `_order_key`
  （挤出 300 分 > 推动 60/子 > 大组 20/子 > 中心性）。
- ⚠️ **截断隐含排序**：`order=False` 但 `max_branch` 会实际发生截断时**也必须先排序**。
  否则按"先单子、后连子"的生成顺序截，会把推挤类着法系统性砍光；
  MCTS 传的正是 `order=False`，实测连"白送一枚挤出"都进不了搜索树。
- `is_legal` 一律重算 `_plan`，**不比对缓存列表**。
- `apply`：不动入参、子数守恒（盘上 + out 恒 28）、挤出计数、`winner_player` 是玩家索引。
- `rollout_move`：90% 直接取能挤出的着法，35% 取能推的，否则按 `_rollout_score` 取前 20% 随机。
  纯随机走 300 手双方各只挤出 1~2 枚 → 价值信号全指望评估函数。
- `settings_map = {"abalone_setup": "setup", "first_player": "first_player"}`。

## 评估（`heuristic.py`）

- `MATE = 100_000.0`；`DEFAULT_WEIGHTS = {w_abalone_out: 220, w_abalone_center: 6,
  w_abalone_cohere: 2.5, w_abalone_danger: 3}`（权重前缀必须带 `abalone`，
  `w_center` 已被四子棋占用）。
- 每一项写成 `w * (f(我方) - f(对方))` → 反对称由构造成立，**不能有 tempo 项**。
- `w_abalone_danger` 用 **ring 的平方**：线性的"Σ ring"与"Σ(4-ring)"只差常数、信息重复。
- 终局返回 ±MATE。**手搭局面只设 `out=(6,0)` 不会返回 MATE** ——
  `winner_player` 不会自动推导，得走一次真实 `apply` 让引擎盖章。
- 实测非终局分数上限 ~725（落后 3 枚），别把 `w_abalone_out` 调到让 `|score| > 1500`。

## 视图（`view.py`）

- `layout()`：`cell = max(10, int(min(area.w/BOARD_UNIT_W, area.h/BOARD_UNIT_H)) - 1)`；
  `origin` = 包围盒左上角；`_center` = 包围盒中心。`cell_center` 只有一处做坐标换算。
  **`origin` / `cell` 属性名不能改**（`tests/ui/helpers.py:pos_for()` 依赖）。
- `pos_at()` 用 cube round + `on_board` 校验（`MatchScene` 用未内缩的 `board_area`
  做 `collidepoint`，视图一定会收到棋盘外坐标）。
- **两段式点击**状态机：`_sync_state` / `_select` / `_target_cell` / `handle_motion` / `handle_click`。
  1) 点己方子 → 选中 1 子组并列出目标格；2) 点同线己方子 → 扩成 2/3 子
  （点已选中的端点可缩回；点不共线的以它重新起组）；3) 点目标格 → 出招。
  `_targets` 是 `{目标格: (move, kind)}`，`kind` 0/1/2 = 普通/推动/挤出。
  `_selected_state is not state` 时清空选择（落子/悔棋/新局都会换局面对象）。
- **提示必须画在棋子之上**（`_draw_cells` → `_draw_marbles` → `_draw_targets` → `_draw_selection`）：
  推挤型着法的目标格本身就是对手棋子所在的那格，先画会被棋子整个盖掉。
- 目标格热区 = **整格**（半径 `cell*0.46`），不是围着选中组画六个小三角
  （小三角热区十几像素、还常被相邻己方子压住，点不中）。
- 棋子调色板索引一律**玩家号 0/1**；滑行中那一组**最后画**（从上一格滑过来，
  先画会被沿途静止棋子盖住）；被挤出盘外的那一枚单独画并淡出。
- `in_placement_mode()` 必须实现并返回 `False`。
- `hover_hint` 文案要短（胶囊自适应宽度，但太长会被裁）：
  "点击一枚己方棋子选中它" / "这一组无处可走，换一组" / "点虚线目标格走子，或再点同线己方子扩组"。

## 测试（`tests/games/abalone/`、`tests/ai/test_abalone_contract.py`、`tests/ui/test_abalone_view.py`）

- 造局面用 `aba_helpers.make_state({(q,r):值}, out=..., current=..., ply=...)`（坐标式、其余自动填）
  或 `parse(9 行棋盘图)`。**文件名叫 `aba_helpers` 而不是 `helpers`**（见 `architecture.md`）。
- 渲染类断言必须"画一帧再取像素"。已锁：61 格像素↔坐标往返、上下/左右朝向、
  两方棋子颜色、目标格提示在棋子之上、滑行动画首帧/落定、
  `(-4,4)`/`(0,-4)` 这类"看着像盘外其实在盘内"的坐标要留意（`max(|q|,|r|,|q+r|) <= 4`）。
- 挤出语义容易写错：沿 E 从 `(2,0),(3,0)` 推 `(4,0)` 的对手子，`(4,0)` 是 `r=0` 行最后一格，
  被推的那枚越界消失、**我方压上的第二枚落在 `(4,0)`（值是 1 不是 0）**，`out` 变 `(1,0)`。
- 推挤规则逐条覆盖：3 推 1 / 2 推 1 / 3 推 2 合法；1 推 1 / 2 推 2 / 3 推 3 非法；
  己方子在后方也算堵住；横移碰对手非法；反向 3 推 1 合法。
- 单子被重复生成、inline 反向忘记 reverse：靠"单子单独生成 + 只用 LINES 表的 2/3 连片段"
  与镜像对称性测试锁住。
- 评估反对称 400 步零违例（逐项单独开权重也测）。
- 稀疏手搭局面（某一方整方清零）会触发 `is_terminal` 的防御性条款 ——
  想验证"还没结束"就给双方各留一枚背景子。
