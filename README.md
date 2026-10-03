# 棋类游戏（boardgames）

**用 Python + Pygame 从零写棋类游戏，顺便把"怎么做"讲清楚。**

一个可插拔的桌面棋类框架 + 四个成品游戏。**依赖只有一个 `pygame-ce`** ——
棋盘几何、AI 搜索、界面控件、动画物理、摄像机全部手写，不引第三方游戏框架 / GUI 库 /
数学库。**规则 / AI / 界面三层解耦**：接入新棋类只需写**规则引擎 + 一块棋盘视图**，
侧栏、主题、控件、AI 调度、悔棋、游戏大厅、规则浮层、设置持久化**全部自动复用**。

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 **Python 3.10+**（`uv` 会按 `.python-version` 自动装好）。
依赖只有一个 `pygame-ce`。

**Windows：双击仓库根目录的 `boardgames.bat`。** 命令行等价写法：

```bash
uv sync && uv run boardgames
```

启动后先进游戏选择大厅，点卡片进入对局；对局中按 `H` 随时查看完整规则。

## 四个游戏

| 游戏 | 玩法特点 |
|---|---|
| **步步为营**（墙棋 / Quoridor） | 9×9，双方各 10 面墙；每回合走一格**或**放一面 2 格长的墙，先到对方底线者胜。墙不能把人完全封死 |
| **重力四子棋**（Connect Four） | 往任意列投子、棋子沿重力下落；横竖斜先连成四子者胜。落子动画是真实的自由落体 + 回弹物理模拟 |
| **大力士棋**（Abalone） | 六边形 61 格，双方各 14 枚；1~3 枚连子整体走一格，**以多推少**把对手 6 枚挤出棋盘者胜。三种官方起始布局 |
| **昆虫棋**（Hive） | **无棋盘**抽象棋，棋盘就是棋子本身；八种虫各有走法（甲虫能爬到棋上、蜘蛛恰好滑三格…），**先围满对方蜂后六面者胜**。无边界画布可拖拽缩放，含官方三枚扩展虫 |

玩法细节、操作方式与快捷键 → [`docs/GAMEPLAY.md`](docs/GAMEPLAY.md)

## 项目结构

```
src/boardgames/
├── core/           游戏无关抽象：State / Move / Game / SearchOptions / GameRegistry（仅标准库）
├── games/<key>/    一个棋类一个包：state / move / rules / heuristic / view（+ geometry / layouts）
├── ai/             engine（统一接口）/ minimax / mcts / tt / random_ai / worker（后台线程）
├── controller/     session.py：对局会话、模式、悔棋、AI 编排
├── settings/       ParamSpec 参数描述 + JSON 持久化
└── ui/             scene / window / chrome / lobby / match_scene / sidebar / settings_panel /
                    rules_panel / camera / animation / theme / fonts / render / board_view / widgets
tests/              按被测层次分目录（core / games / ai / settings / ui）
scripts/            benchmark_ai.py（AI 基准）、fetch_hive_assets.py（昆虫棋素材下载）
docs/               见下表
```

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/GAMEPLAY.md`](docs/GAMEPLAY.md) | 玩法速览、界面说明、操作与快捷键、对局模式与悔棋、AI 简述 |
| [`docs/USAGE.md`](docs/USAGE.md) | 命令行参数、「无边框 / 离屏」两个开关、离屏截图、参数持久化、测试命令、素材授权 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 项目定位、分层与依赖铁律、核心抽象、AI / UI / 设置子系统、坑清单、刻意的取舍 |
| [`docs/ADDING_A_GAME.md`](docs/ADDING_A_GAME.md) | 新增棋类的实操步骤、代码模板、可选钩子与坑清单 |
