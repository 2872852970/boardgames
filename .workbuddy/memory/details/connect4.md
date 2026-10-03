# 细节笔记：Connect Four（规则 + 视图）

## 规则实现要点

- 坐标 `(col, row)`，**row 0 是最底行**。棋盘存一维 `cells`（下标 `row*cols+col`，
  0 空 / 1 玩家1 / 2 玩家2）+ **冗余** `heights`（投子目标行 = `heights[col]`，
  威胁检测要遍历所有列的下一格，从 `cells` 推导是 O(cols×rows)，rollout 里被调用上百万次）。
- **`winner_player` 存玩家索引（0/1）而不是棋子值（1/2）**。引擎会拿 `state.winner()`
  直接和玩家索引比较，用棋子值会让符号整个反过来 —— 实测 minimax 深度 1~6 全部找不到
  "三连直接赢"这种必胜手。
- **字段绝不能叫 `winner`**：`State.winner()` 是 ABC 抽象方法，同名字段会遮蔽它，
  `minimax` 里 `state.winner()` 会拿到非可调用对象。
- `scan_win` **落点两侧的连子数必须相加**再比较 `>= 4`。写成「正反两方向各自独立计数再判断」
  会让"落点补上横四/斜四中间那一子"（`X.XX` → 投中间变 `XXXX`）永远判不出胜负。
- `is_terminal()` 用 `all(h >= rows)` 而非 `ply >= cols*rows` —— 手搭测试局面时
  `ply` 可能与棋盘不同步。
- `zobrist_hash` 排除 `heights` / `ply` / `winner_player`（都能从 `cells` 推出）。
- **收敛性天然成立**：每步必然 `ply += 1` 且棋盘不可逆填满，任何合法序列都在
  ≤ `cols*rows` 步内终止 —— 不像墙棋棋子能来回走，振荡在数学上不可能发生。
- **`legal_moves` 必须完全忽略 `max_branch` 与 `include_walls`**（原因见 `ai.md`）。
- **不能有 tempo（节奏）项**：墙棋里"轮到谁走"有先后优势，四子棋没有（先手优势已体现在
  先落子的棋子上）。加这一项会破坏 `evaluate(s,0) == -evaluate(s,1)`，minimax 在双方都
  不占便宜的局面里乱选。同理攻/防威胁必须**共用一个权重**（`w_threat`）。
- 评估分**对称性有回归测试**锁住（`evaluate(s,0) == -evaluate(s,1)`）。
- **`count_pieces()` 别用"总格数 − 已落子数"算对手** —— 那是**空格数**，空盘会报"对手已落 42 子"。
  正确写法 `heights_total() - p0`。
- **调色板索引一律用玩家号 0/1**（`theme.PLAYER_COLORS` 只有 2 项）。写成 `棋子值 = 玩家号 + 1`
  会让**玩家 2 悬停**（`_draw_ghost`）和**玩家 2 赢棋**（`_draw_win_line`）直接 IndexError。

## 视图（渲染层最易错）

- **局面行号与屏幕行号是反的**：`row == 0` 是最底行，屏幕 y 向下增大。
  翻转只在 `Connect4View.screen_row(row) = rows - 1 - row` 一处做，`cell_center` 内部用它。
  **两处各翻一次 = 没翻**（症状：整盘棋子堆在棋盘顶部）。
- **`Game` 侧只提供"谁能赢"的语义，视图不实现规则**；但渲染类 bug（上下颠倒、差半格）
  用断言数据结构的测试**永远抓不到** —— 必须"画一帧再取像素"：
  `surface.get_at(view.cell_center(col, 0))[:3] == theme.PLAYER_COLORS[0]`。
- 落子预览（ghost）必须与圆窝**同心同径**：中心就是 `cell_center(col, heights[col])`，
  半径就是 `socket_radius`。给它加"浮在上方"的纵向偏移 = 看着没对准。
- **正在下落的那一枚要最后画**：它要穿过已有棋子掉到槽位，先画会被沿途棋子盖住。
- 高亮跟**最后一手**（`_last_move`）走，不给当前行动方的所有棋子加光环 —— 颜色已经说明归属。

## 测试的坑

- `tests/games/connect4/c4_test_*.py` **文件名不符合 pytest 默认规则**，85 项从未被自动收集。
  若要启用，改名成 `test_*.py` 即可（未做，避免一次性冒出 85 个未验证用例）。
