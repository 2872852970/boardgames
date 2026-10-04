# 运行与开发

安装、启动、命令行参数、调试手段与测试。玩法与操作见 [`GAMEPLAY.md`](GAMEPLAY.md)。

---

## 1. 安装与启动

需要 [uv](https://docs.astral.sh/uv/)。**Python 版本：3.10 及以上**（项目就在 3.10 上开发；
`uv` 会自动按 `.python-version` 装好对应版本）。依赖只有一个 `pygame-ce`。

> 3.10 这条线是刻意选的：`dataclass(slots=True)`、`zip(strict=)`、`X | Y` 运行时联合类型
> 都是 3.10 才有，而这三样在搜索热路径上天天用；pygame-ce 2.5.7+ 也要求 3.10。
> 唯一用不了的是 PEP 695 泛型（要 3.12），所以代码里统一写 `TypeVar` + `Generic`。

**Windows 上最简单的跑法：双击仓库根目录的 `boardgames.bat`。** 它做的事是
`cd /d %~dp0` → 检查 `uv` → 设好两个环境变量 → `uv run python -m boardgames.app %*`，
失败时会停住让你看清错误。

> #### 为什么 bat 里非要设 `PYTHONUTF8=1`
> 项目路径**含中文**时（比如 `C:\Users\Admin\WorkBuddy\棋类游戏`），双击启动会直接报
> `ModuleNotFoundError: No module named 'boardgames'`。
>
> 链条是这样的：uv 把本项目以 editable 方式装进 `.venv`，往
> `.venv\Lib\site-packages\_editable_impl_boardgames.pth` 里写下一行 **UTF-8 编码**的
> `C:\...\棋类游戏\src`；而 Python 的 `site.py` 在 Windows 上读 `.pth` 用的是
> **系统 ANSI 编码（GBK/936）**，解出一个乱码路径 → 该目录不存在 → 被 `site` 静默忽略
> → `src` 不在 `sys.path`。
>
> 开 UTF-8 模式（PEP 540）后 `.pth` 按 UTF-8 读，问题解决；`PYTHONPATH` 再兜一层底。
> 命令行下碰到就自己补一句 `set PYTHONUTF8=1`（PowerShell 里是 `$env:PYTHONUTF8=1`）。
>
> 顺带两个批处理自身的坑：`boardgames.bat` 存成 **UTF-8 但正文保持纯 ASCII**
> （cmd 用系统代码页解 `.bat`，非 ASCII 字节会变乱码，所以没写 `chcp 65001`——
> 它在某些终端环境里还会挂起），并且 `.gitattributes` 里钉了 `*.bat text eol=crlf`。

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
uv run boardgames --game dotsboxes                      # 点格棋（点阵尺寸在侧栏调 3~9）
uv run boardgames --game mancala                        # 播棋（坑数/种子数在侧栏调）
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
uv run boardgames --offscreen --screenshot db.png  --game dotsboxes --scene match --demo 25 --hover dots-edge
uv run boardgames --offscreen --screenshot mc.png  --game mancala   --scene match --demo 15 --hover mancala-pit
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

其中"改了必须重开一局"的键（棋盘尺寸、每人墙数、起始布局、扩展虫、点阵尺寸、播棋坑数/种子）都注册在
`RESTART_KEYS` 里；对局一旦落子，这些参数在界面上会被锁定（见 [`GAMEPLAY.md`](GAMEPLAY.md) §1）。

---

## 6. 测试

```bash
uv run pytest                # 全部（约 45 秒）
uv run pytest -m "not slow"  # 只跑快的：规则 / UI / 参数 / 设置（几秒）
uv run pytest -m slow        # 只跑耗时的：AI 搜索契约、整局 rollout 收敛
uv run pytest tests/games    # 只跑规则
uv run pytest tests/ui       # UI 冒烟（SDL dummy 驱动，不需要显示器）
uv run ruff check src tests scripts
```

`tests/conftest.py` 会**按路径**给耗时用例自动打 `slow` 标记（跑真 AI 搜索的 `tests/ai/`、
跑整局模拟的 `*rollout*`）。所以日常改一两个小地方时用 `-m "not slow"` 就够了 ——
**只在动了规则、评估函数或引擎之后才需要跑全量**，别让每次微调都等上一轮 AI 对弈。

覆盖重点与"为什么要这么测"见 [`ARCHITECTURE.md`](ARCHITECTURE.md) §8。

---

## 7. 素材与授权

昆虫棋的八种昆虫图标来自 **[OpenMoji](https://openmoji.org/)**（CC0 1.0 公共领域贡献），
位于 `games/hive/assets/`，下载脚本 `scripts/fetch_hive_assets.py` 可离线重跑。
运行时按玩家色**重新着色**，所以同一套图标能同时表达双方；
**素材缺失时自动退回程序绘制的兜底图形**，不会白屏。完整来源见 `assets/CREDITS.md`。
