# 细节笔记：昆虫棋（Hive）

规则出处：<https://theworldatplay.com/zh-CN/games/hive>（+ 官方 FAQ 的 freedom of movement）。
文件：`games/hive/{geometry,pieces,state,move,rules,heuristic,view}.py` + `assets/`。

## 与其它三个棋类的结构差异（先看这条，别照抄 abalone 的写法）

| | 墙棋 / 四子棋 / 大力士棋 | 昆虫棋 |
|---|---|---|
| 棋盘 | 定长数组（`h_mask` / `heights` / 61 格） | **无边界**：`Pos -> 栈` 的映射 |
| 一格 | 一个值 | `tuple[Piece, ...]`（底 → 顶，**可叠层**） |
| 手牌 | 无 | 存**配额**，手牌由"配额 − 盘上数量"推导 |
| 停一手 | 不存在 | **`PassMove` 是合法着法** |
| 胜负 | 走到对面 / 连四 / 挤出 6 | 对方蜂后**六面被占满**（敌我棋子都算） |

状态是 `HiveState`，`__post_init__` 里建好 `_index`（`Pos -> 栈`）与 `_hands` 两个缓存
（`compare=False`，不参与相等性）。**解析式手牌**是刻意的：杜绝"手牌与盘面不同步"。

## 死规则清单（每条都有测试）

1. **第一枚落在世界原点 `(0,0)`**（`initial_state` 之外的地方不可能出现第一枚）。
2. **放置：必须贴至少一枚己方、不得贴任何敌方**。判定看 `state.owner_at(pos)`（= **栈顶**归属）
   —— 甲虫爬到对方棋上之后那一格就"变成甲虫那边"，于是放置判定不需要任何特判。
3. **蜂后期限**：自己第 4 回合结束前必须落盘（`QUEEN_DEADLINE`，看 `state.played[player]`）。
4. **蜂后没落盘 → 一枚棋都不能移动**（不是"只有蜂后不能动"）。
5. **一体规则**：拿走一枚棋之后剩下的棋必须连通。快速路径：叠层上放行 / 邻居 ≤1 放行 /
   邻居 2 且彼此相邻放行 / ≥3 才跑 BFS。
6. **滑动门**：`min(hC, hD) > max(hsrc, hdst)` 时挤不过去；高度取**取走移动棋之后**的层高；
   **叠层上的棋不看门**（它从顶上走）。带 `from_height/to_height` 的着法**相等性不含层高**。
7. **胜负**：蜂后六面全被占 → 输；**被甲虫压住的格子照样算占**（压在上面的那枚棋本身占位）；
   己方棋占自己的邻格也算。双方同一手同时被围满 → 判和（`drawn`）。
8. **和棋四条路**：双方同时围满 / 同一（规范化）局面第三次出现 / 连续两 PassMove / `MAX_PLY=400`。

## `PassMove`——最容易漏的一环

`is_terminal()` 是 **O(1)**（只看 `winner_player` / `drawn`），**绝不在这里跑着法生成**。
于是"该方无处可走"不会自动成为终局，必须由 `legal_moves` **显式返回 `PassMove`**。
`rollout_move` 也永远返回合法着法，绝不返回空表 —— 否则 MCTS rollout 空转到抛错，
`AIWorker._run` 把异常吞掉，表现就是 **"AI 突然不下棋了"**。
新增的 `tests/ai/test_hive_contract.py` 专门锁这条："只能 pass 的局面四个引擎都必须交 `PassMove`"。

## 几何

pointy-top + axial `(q, r)`；`DIRECTIONS = ((1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1))`；
`axial_to_pixel = (size*√3*(q + r/2), size*1.5*r)`；`pixel_to_axial` 用 cube round + **half-up**
（`math.floor(v + 0.5)`）—— 用 Python 的 `round()`（banker's rounding）会让边界格随机跳。
**整套换算只有 `view.world_of()` / `view.pos_at()` 两个出口**，别在别处另写一份。

## 平移不变性

`HiveState.zobrist_hash()` 先做 `_canonical()`（整体平移到最左下的格在 `(0,0)`）再哈希，
并且**只哈希 `stacks + current`**，不含 `ply/seen/passes`。不归一化会让置换表与 MCTS 的
节点复用全部失效，甚至把不同局面误判成同一局面。第一枚棋钉在世界原点，所以实测几乎恒等，
这层是纯保险。

## 着法与排序（`rules.py`）

- `PlaceMove(kind, dest)` / `MoveMove(src, dest, kind)` / `PillbugMove(src, dest, carried, carried_dest)`
  / `PassMove(player)`。动画附带信息（`kind` / 高度 / 被搬的棋）一律 **`compare=False`**。
- **`destinations()` 的语义是"目标格"**：`PillbugMove` **只报 `carried_dest`** ——
  鼠妇自己 `dest == src` 不挪窝，把 `dest` 报出去会点亮没动的格子（真 bug，已修）。
- `_OrderContext`：`list.sort(key=...)` 的键函数**不能每帧重算 `occupancy()`**，
  预先算好 `around_opp` / `queen_pos`，键退化成纯算术。末尾带 `(dest[0], dest[1])` 保证
  排序**完全确定**（同分不能随哈希随机化乱序）。制胜手 `+1e6` 保证不被 `max_branch` 裁掉。
- `_dedup()` 用**复合键**去重：`(dest,)` 或 `(dest, carried, carried_dest)`。
  只按 `dest` 去重会把鼠妇的八种搬运合并成一手。

## 视图（`view.py`，唯一 import pygame 的模块）

- **坐标只在一处换算**：世界格 → `cell_center(pos, height)`（叠层上抬 `STACK_LIFT` + 缩小
  `STACK_SHRINK`）→ 屏幕。缩放**全部**归 Camera，视图里没有 zoom 概念。
- 素材：`_load` 缓存 + OpenMoji 白模化（`pygame.mask`）→ 剪影染 `PLAYER_COLORS`、
  线稿染 `PLAYER_DARK` 叠上 → `sprite(kind, player, radius)`（`_SPRITES` 缓存上限 240 后 clear）。
  **加载失败走 `_procedural()` 兜底**，不白屏。
- 绘制剔除：只画"有棋的格 + 它们的外圈"，按 `camera.visible_world_rect()` 过滤
  —— 无限棋盘不可能全画。
- 动画拿到的是**走完之后**的局面（`view.animate(move)` 先于 `session.play(move)`），
  所以 `_Anim` 存的是**世界格路径 + hidden 集合 + from/to_height**，屏幕坐标每帧现算。
- 手牌条：`HAND_LABEL_W = 30` 是给「手牌」两个字的**专属窄条**（不留给会被卡片盖住，真 bug）；
  卡片只显示当前行动方的手牌，余量角标在 `>1` 时才画；右上胶囊报**双方**余量，
  用"玩家1/玩家2"而不是"我/对手"（自对弈时没有"我"）。
- `hud_inset()` 返回 `HAND_H + 26`：把手牌条从底部提示的站位里让出来。

## 摄像机（`ui/camera.py`，框架级）

`screen = world * scale + offset`，`offset` 是**世界原点在屏幕上的位置**。

- `fit(rect, padding, max_scale)` 的 `max_scale` 是**软上限**：开局包围盒只有 7 格，
  不设上限会把一枚棋放大到铺满画布。树里用 `1.06`。
- `CameraController` 裁决点击 vs 拖拽：按下→扣住→松手时按**累计位移**判（`DRAG_SLOP=4`px），
  `CONSUME` 吞掉事件、`CLICK` 才交给视图。**没有它，"手抖一下"就会误落子或平移后误点。**
- `MOUSEWHEEL` 事件在测试里可能没有 `pos` → 用 `getattr(event, "pos", None) or pygame.mouse.get_pos()`。
- 视图侧可选钩子（全是 `hasattr` 探测，老棋类零改动）：`camera` / `camera_viewport()` /
  `auto_fit_camera(state)` / `hud_inset()` / `idle_hint()` / `world_bounds(state)` /
  `hover_hint()` / `hud_hint()`。
- `MatchScene`：`verdict == CONSUME` 直接 return；`F` 键 `_fit_camera()`；重开一局 / 悔棋时
  `camera.auto_fit = True` 把镜头交回去。**只有按 F 或重开才收回控制权**（玩家一上手就交还）。

## 素材来源

OpenMoji（<https://openmoji.org/>）CC0 1.0，见 `games/hive/assets/CREDITS.md`。
下载脚本 `scripts/fetch_hive_assets.py` 走 jsdelivr `/gh/` 代理 + 4 镜像轮换，
统一裁剪框 + `smoothscale` 到 192×192，**零新依赖**。

## 调参建议（实测）

分支因子：ply1 5 → ply10 51 → ply20 **101** → ply40 77；`legal_moves` 0.18ms。
Minimax d4 b16 **141ms** / d6 b16 1206ms（1200ms 时限够用）；MCTS 只有 **~83 nps**
（rollout 每步都要生成长着法表，四个棋类里最慢）。**昆虫棋优先用 Minimax**（d4~6、候选 16~32），
MCTS 建议只当陪练；`p_hive_place`（rollout 放置概率，默认 0.55）调低会变成双方互相搬家不围后。

## 截图 / 自查

```bash
uv run boardgames --game hive --scene match --mode pvp --headless --demo 16 \
  --hover hive-place --screenshot .workbuddy/artifacts/hive_place.png
```

**必须显式 `--mode pvp`**：落点提示挂在 `interactive` 上，`config/settings.json` 里若存了
`mode=eve`，默认命令会拍到"一个落点都没有"的画面（这不是 bug，是自对弈没有交互权）。
`--hover` 的两个取值：`hive-place`（选手牌卡，挑**还有货**的卡）/ `hive-select`（选棋子）。
