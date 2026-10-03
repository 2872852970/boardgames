# 昆虫棋棋子素材

来源：**[OpenMoji](https://openmoji.org)** —— 许可 **CC0 1.0**（公有领域贡献）。
获取日期：2026-10-03。

每个虫种两个文件：

* ``<kind>.png`` —— **实心剪影**，取自 OpenMoji **color** 变体的 alpha 通道；
* ``<kind>.line.png`` —— **线稿细节**（轮廓 + 斑点 + 体节），取自 **black** 变体。

运行时的画法是：剪影染成玩家亮色当底，线稿染成玩家深色叠在上面 ——
于是得到"扁平填色 + 深色描边细节"的棋子，与木质棋子的观感接近。

## 清单

| 文件 | 虫种 | code point | 备注 |
|---|---|---|---|
| `queen.png` / `queen.line.png` | 蜂后 | 1F41D | 蜜蜂 🐝 |
| `beetle.png` / `beetle.line.png` | 甲虫 | 1FAB2 | 甲虫 🪲 |
| `grasshopper.png` / `grasshopper.line.png` | 蚱蜢 | 1F997 | 蟋蟀 🦗（蚱蜢无独立 emoji，用同目昆虫代替） |
| `spider.png` / `spider.line.png` | 蜘蛛 | 1F577 | 蜘蛛 🕷 |
| `ant.png` / `ant.line.png` | 兵蚁 | 1F41C | 蚂蚁 🐜 |
| `ladybug.png` / `ladybug.line.png` | 瓢虫 | 1F41E | 瓢虫 🐞 |
| `mosquito.png` / `mosquito.line.png` | 蚊子 | 1F99F | 蚊子 🦟 |
| `pillbug.png` / `pillbug.line.png` | 鼠妇 | 1FAB3 | 蟑螂 🪳（鼠妇无 emoji，用体型最接近的代替） |

## 处理流程

`scripts/fetch_hive_assets.py`：

1. 下载 OpenMoji **color** 与 **black** 变体的 618×618 PNG（走 jsdelivr 的
   `/gh/` 代理，因为 `raw.githubusercontent.com` 在部分网络环境下不通）；
2. 用 `pygame.mask` 抠出 alpha 通道 → **纯白模**（RGB 恒为 255，alpha 保留轮廓）；
   两张图**共用同一个裁剪框**，保证叠加不偏移；
3. 裁掉四周空白，四周留 6% 余量，居中成正方形；
4. `smoothscale` 到 192×192（3.2× 降采样把二值边缘重新平均成抗锯齿）。

白模化是运行时着色的前提：视图里 `fill(玩家色)` 再 `BLEND_RGBA_MULT` 一行
就能把整枚棋子染成玩家色。

## 兜底

素材缺失时（比如没跑过这个脚本、或者离线环境），`HiveView` 里的
`_Sprites._fallback()` 会用 `pygame.draw` 现画一枚可区分的虫形，
游戏与测试都能正常跑。
