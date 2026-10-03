# 运行与开发

安装、启动、命令行参数、调试手段与测试。玩法与操作见 [`GAMEPLAY.md`](GAMEPLAY.md)。

---

## 1. 安装与启动

需要 [uv](https://docs.astral.sh/uv/)（Python 3.13）。依赖只有一个 `pygame-ce`。

**Windows 上最简单的跑法：双击仓库根目录的 `boardgames.bat`**（内容就是 `uv run boardgames`）。

命令行等价写法：

```bash
uv sync              # 安装依赖
uv run boardgames    # 启动（先进游戏选择大厅）
```

---

## 2. 常用命令行参数

```bash
uv run boardgames --game connect4                       # 直接进某个棋类
uv run boardgames --scene match                         # 跳过大厅直接进对局
uv run boardgames --mode eve --p1 mcts --p2 minimax     # AI 自对弈
uv run boardgames --game connect4 --cols 8 --rows 7     # 自定义四子棋盘
uv run boardgames --game quoridor --size 11 --walls 15  # 自定义墙棋棋盘
uv run boardgames --window 1000x640                     # 强制窗口尺寸（小屏 / 调试布局）
uv run boardgames --windowed                            # 用系统标题栏（默认是无边框）
uv run python scripts/benchmark_ai.py                   # AI 性能基准
```

窗口默认 1180×780，会自动裁剪到不超过屏幕可用区域；可自由缩放，
侧栏在小窗口下自动收窄并可滚动。

---

## 3. 「无边框」和「不显示窗口」是两个开关

| 开关 | 含义 |
|---|---|
| `--frameless`（别名 `--headless`） | **无边框窗口**：不要系统标题栏，改由程序自己画一条（标题 / 最小化 / 全屏 / 关闭 / 拖动），**窗口照常显示、照常能玩**。默认开启（也可在「设置 → 界面与操作 → 无边框窗口」里关掉，改完需重启程序）。 |
| `--offscreen` | **完全不显示窗口**：切 SDL dummy 驱动跑主循环，给 CI / 容器 / 跑批用。真的开不出窗口时（无 `DISPLAY`、远程桌面断开）也会自动降级到它。 |

混成一个的后果是"想去掉标题栏的人得到了一个看不见的窗口"。
无边框下拖动窗口只在 Windows 生效（借的是系统能力 `WM_NCLBUTTONDOWN` + `HTCAPTION`），
其他平台拖不动，但三个按钮与快捷键都正常，不抛异常也不卡住。

---

## 4. 离屏截图（自检 / 看布局）

```bash
uv run boardgames --offscreen --screenshot lobby.png --scene lobby
uv run boardgames --offscreen --screenshot c4.png  --game connect4 --scene match --demo 8  --hover drop
uv run boardgames --offscreen --screenshot q.png   --game quoridor --scene match --demo 6  --hover wall-h
uv run boardgames --offscreen --screenshot aba.png --game abalone  --scene match --demo 24 --hover aba-select
uv run boardgames --mode pvp --offscreen --screenshot hive.png --game hive --scene match --demo 18 --hover hive-place
```

> 昆虫棋截图**必须加 `--mode pvp`**：落点提示挂在交互态上，配置里若存了 `mode=eve`，
> 会拍到"一个落点都没有"的画面。昆虫棋棋盘无边界，截图前会自动把镜头拉回蜂巢（等于按 `F`）。

离屏模式配合 `--until-over` 可以一直跑到分出胜负（自动解除自对弈的暂停、关掉动画、
放开帧率，默认真实时间上限 600s，用 `--timeout` 调）；`--fast-ai` 把 AI 调成演示速度
（只改本次运行，不写回配置文件）。

---

## 5. 参数与持久化

侧栏改的任何参数都会**立刻生效**并自动持久化到 `config/settings.json`（防抖 600ms 落盘）。
参数表由 `settings/schema.py` 的 `ParamSpec` 驱动 —— 想加一个可调参数，
只要在那里加一行；标上 `games=("key",)` 就只在该棋类出现。

其中"改了必须重开一局"的键（棋盘尺寸、每人墙数、起始布局、扩展虫、先手）都注册在
`RESTART_KEYS` 里；对局一旦落子，这些参数在界面上会被锁定（见 [`GAMEPLAY.md`](GAMEPLAY.md) §1）。

---

## 6. 测试

```bash
uv run pytest              # 全部
uv run pytest tests/games  # 只跑规则
uv run pytest tests/ai     # 只跑 AI 契约
uv run pytest tests/ui     # UI 冒烟（SDL dummy 驱动，不需要显示器）
uv run ruff check src tests scripts
```

覆盖重点与"为什么要这么测"见 [`ARCHITECTURE.md`](ARCHITECTURE.md) §8。

---

## 7. 素材与授权

昆虫棋的八种昆虫图标来自 **[OpenMoji](https://openmoji.org/)**（CC0 1.0 公共领域贡献），
位于 `games/hive/assets/`，下载脚本 `scripts/fetch_hive_assets.py` 可离线重跑。
运行时按玩家色**重新着色**，所以同一套图标能同时表达双方；
**素材缺失时自动退回程序绘制的兜底图形**，不会白屏。完整来源见 `assets/CREDITS.md`。
