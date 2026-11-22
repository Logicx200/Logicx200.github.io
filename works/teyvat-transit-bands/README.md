# 提瓦特的凌日 / 凌月带

用游戏内已知目标（天空岛、群玉阁、寒天之钉）反推提瓦特天空的日月轨迹，并画出它们的凌日带与凌月带。

**在线交互地图：** [index.html](index.html)（单文件，可缩放/平移、切换目标与底图）

## 结论

| 目标 | 位置 (x, y) | 高度 | 带偏移（南） | 带宽 | 凌日 / 凌月 |
|---|---|---|---|---|---|
| 天空岛 | (−3383, +21) | 1.5 km | 600 m | ≈196 m | 12:00 / 00:00 |
| 群玉阁 | (−1201, +3164) | 300 m | 120 m | ≈60 m | 12:00 / 00:00 |
| 寒天之钉 | (+142.5, +1364) | 400–696 m | 160–280 m | ≈120 m+ | 12:00 / 00:00 |

- 日月轨迹最高只到 **68.2°**，不过天顶，所以带都落在目标**正下方以南**，偏移 = 高度 ÷ tan 68.2° ≈ 0.4 × 高度；
- 太阳带正东西，月亮带偏 **10°**（升 80°/落 260°）；
- 两带的交点**不是**目标本身，而是目标正下方以南的那个点；
- 寒天之钉是竖长的钉体，钉底与钉顶的影子落点不同，带因此被“拉宽”。

## 方法

1. 从观测枢锚点表中取天空岛、群玉阁、寒天之钉的水平坐标；
2. 用天空岛的偏移（1.5 km → 600 m）反推日月轨迹最高高度角 68.2°；
3. 同一片天空下，其余目标的带偏移按高度线性缩放；
4. 带宽由目标的横向尺度（足迹）与高度跨度共同决定；
5. 用世界坐标（+x 东、+y 南，米）把带画在地图上。

## 文件

- `index.html`：交互地图（内嵌完整 8K 官方大地图底图与简图底图）；
- `figures/`：天空岛合成图、天空岛高度角热力图、群玉阁大范围图、群玉阁与寒天之钉热力图；
- `data/bands.csv`：三个目标的带参数。

## 不确定度

- 群玉阁、寒天之钉的水平位置取观测枢点，可能有几十到几百米误差；
- 寒天之钉底部高度按山体约 400 m 估；
- 若实测日月最高高度角不是 68.2°，所有偏移按 `高度 / tan(a_max)` 缩放。

## English summary

Transit bands of three floating landmarks in Teyvat (Celestia, Jade Chamber, Skyfrost Nail). The sun/moon path peaks at 68.2° (not the zenith), so each transit band lies ~0.4×height south of the target; the solar band runs E-W and the lunar band is tilted 10°. The interactive map is a single self-contained HTML file with the full 8K official map and a clean basemap.
