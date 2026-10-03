# 细节笔记：AI 层（引擎契约 / 调参 / 各棋类 rollout）

## 引擎契约

- `SearchOptions(max_branch=16, order=True, include_special=True, include_walls=True)`。
- **`include_walls` / `include_special` 是墙棋专用**：`include_walls` 决定要不要生成墙分支；
  `include_special` 是 minimax 的 `include_walls = ply < wall_depth` 派生。
  四子棋与大力士棋**一律忽略** —— 当成"裁剪着法"会让深度 ≥2 的节点只剩 ≤1 个着法，
  棋力直接崩却查不出原因。
- **`max_branch` 只对"组合爆炸型"棋类有意义**：四子棋忽略它（分支本来就小）；
  墙棋用它限制**候选墙数量**（走子永远全部展开）；**大力士棋是唯一真正需要它的**
  （开局 44~80 步）。
- **`max_branch` 是"从列表头部截断"**，所以**截断必须隐含排序**，否则被裁掉的是
  生成顺序里靠后的那批，而 MCTS 传的正是 `order=False`。
  大力士棋里这直接把推挤类着法系统性砍光（实测连"白送一枚挤出"都进不了搜索树）。

## 墙棋（Quoridor）

- 墙分支上百，必须裁剪：只取**对手最短路径**上每条边对应的锚点，按"对手路径增量"降序取前 N 个；
  深层（`wall_depth` 之外）只展开走子。
- rollout 必须单调推进：用 `geometry.distance_field`（多源 BFS + `lru_cache`）选步，
  不要用曼哈顿距离贪心（会振荡、棋局不收敛）。已有回归测试锁住这一点。
- `legal_moves` 的顺序是 **走子在前、墙在后**，所以 `max_branch` 会先吃掉墙候选。
  `order=True` 时走子会按"走后己方最短路径"重排（要跑 `shortest_path`，不便宜）。

## MCTS

- 子节点 `mean` 是**子节点行动方视角**，`best_child` 用 `-child.mean` 取负才是本方视角；
  最终选步要按 `node.player == root_player` 翻符号。
- 用"越早取胜回报越高"塑形（`speed = max(0.5, 1 - depth/(2*cap))`），否则胜率接近 1 时会来回拖延。
- rollout 循环的出口只有 `is_terminal()` 与 `depth < cap`。**游戏若存在"非终局但无处可走"
  的局面，rollout 会一直索取着法直到抛 `RuntimeError`**（`AIWorker._run` 吞掉异常，
  表现是"AI 突然不下棋了"）。所以各游戏的 `is_terminal()` 要把这种情况算进去。
- `_MCTSRun.options = SearchOptions(max_branch=..., order=False, include_walls=True)`。
- MCTS 实测 1.2s ≈ 620~720 次迭代（墙棋）；Minimax depth 4 ≈ 80ms。

## ROLLOUT_VALUE_SCALE = 600

**不要动这个常量。** 它是给墙棋调的（墙棋 `w_path=100`/步，评估分轻松上百）。
四子棋/大力士棋评估分小得多，但实测没问题：

- 四子棋（2026-10-03）：minimax depth6 vs mcts 4000iter 各 8 局 4:4，0 平；
  两者都能抓住必胜与必防。四子棋 rollout 策略本身够强（贪心 + 威胁优先 + 中心加权随机）。
- 大力士棋（2026-10-03）：minimax depth4 × 400ms vs mcts 400ms，三种布局各一局，
  49~67 手内全部分出胜负（minimax 全胜）。评估分实测最大 ~725（落后 3 枚），
  `tanh(725/600)=0.84` 仍有梯度。**评估分本身不要调到 |score| > 1500**，
  否则回报会被 tanh 拍平成 ±1。

## 调参默认值（实测）

| 项 | 默认 |
|---|---|
| minimax | depth 4 / wall_depth 2 / 1200ms / 着法候选上限 12 |
| mcts | 43500 次迭代上限 / 1200ms / 着法候选上限 8 / rollout 深度上限 40 |

- 大力士棋的候选上限**建议 20~32**（开局 44 步），侧栏 hint 里写了。
- 大力士棋的 rollout 必须**强烈偏向推挤**（90% 直接取能挤出的着法），
  否则纯随机走 300 手双方各只挤出 1~2 枚，价值信号全指望评估函数。

## 无头冒烟 / 调试命令

```bash
uv run boardgames --headless --screenshot out.png --demo 20 --scene match   # 拍中局
uv run boardgames --headless --screenshot lobby.png --scene lobby           # 拍大厅
uv run boardgames --window 1000x640                                        # 调试布局
uv run boardgames --hover wall-h --scene match                             # 模拟悬停（按棋类分派）
uv run boardgames --hover aba-select --game abalone --scene match          # 大力士棋：选中+悬停
uv run boardgames --game abalone --scene match --demo 24 --frames 40       # 走到中局再拍
uv run python scripts/benchmark_ai.py
```
