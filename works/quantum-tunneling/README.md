# 量子隧穿理论模型：穿透概率计算与时域仿真动画

一维方势垒量子隧穿的完整数值实验：解析穿透概率、WKB 近似、独立的散射求解器、
以及基于含时薛定谔方程的分步傅里叶时域波包仿真与动画。

**详细结果与数据表见 [`REPORT.md`](REPORT.md)。**

## 快速开始

```powershell
cd quantum_tunneling
python selftest.py          # 先跑自检: 22 项交叉验证 (约 2 分钟, 退出码 0 为全部通过)
python param_sweep.py       # 生成 fig1-fig6 参数扫描图
python make_animation.py    # 生成 4 个时域仿真 GIF 动画 + 关键帧 + 时间序列
python make_compare.py      # 生成场景对比图
python report_data.py       # 打印报告用定量表格
```

依赖：NumPy、Matplotlib、Pillow（当前环境 Python 3.11.5 / NumPy 2.2.6 / Matplotlib 3.10.0 / Pillow 11.1.0）。

## 物理与数值设定

自然单位 $\hbar=m=1$，方势垒 $V(x)=V_0\,(|x|<a/2)$。解析透射系数

$$T(E)=\frac{1}{1+\dfrac{V_0^2}{4E(E-V_0)}\sin^2(k_1a)},\qquad
T(E<V_0)=\frac{1}{1+\dfrac{V_0^2\sinh^2(\kappa a)}{4E(V_0-E)}}$$

时域仿真：高斯波包（$\sigma=8$，$x_0=-60$，$k_0=1.8$），网格 $N=16384$、$L=400$、
$\Delta x=0.0244$，$\Delta t=0.0025$，势垒边缘以 $1.5\Delta x$ 的 $\cos^2$ 斜坡平滑。

## 结果速览

| 场景 | $V_0$ | $a$ | $E_0$ | 数值 $T$ | 解析 $T(E_0)$ | 谱平均 $\langle T\rangle$ | 动画 |
|---|---|---|---|---|---|---|---|
| 薄垒 | 2.0 | 0.4 | 1.620 | 0.82881 | 0.82942 | 0.82897 | `animations/tunneling_barrier_a0.4.gif` |
| 中等隧穿 | 2.0 | 1.0 | 1.620 | 0.38822 | 0.38748 | 0.38813 | `animations/tunneling_barrier_a1.0.gif` |
| 厚垒 | 2.0 | 3.0 | 1.125 | 0.001542 | 0.001405 | 0.001543 | `animations/tunneling_barrier_a3.0.gif` |
| 越顶 | 1.0 | 1.0 | 1.620 | 0.83215 | 0.83306 | 0.83213 | `animations/tunneling_above_barrier.gif` |

透射率随垒高/垒宽在本次扫描范围内跨越约 **10 个数量级**（$9.85\times10^{-1}$ 到
$7.6\times10^{-11}$）。

## 验证要点

- 解析闭式解 vs 独立散射求解器（72 组参数）：max$|\Delta T|=8.2\times10^{-13}$
- 界面连续性残差 $1.6\times10^{-11}$；概率守恒 $|t|^2+|r|^2-1=7.8\times10^{-16}$
- 时域仿真 vs 解析谱平均（$T\gtrsim10^{-3}$）：偏差 0.002%–0.5%
- 时间步与网格收敛性已检查；发现并处理了两个数值陷阱（点取样阶跃势的量化误差、
  吸收边界导致的概率不守恒），详见 `REPORT.md` §3.1

## 文件结构

```
tunneling_core.py        计算核心: 解析解 / 独立求解器 / WKB / 谱平均 / 分步傅里叶演化
selftest.py              22 项交叉验证自检
param_sweep.py           参数扫描 (fig1-fig6)
make_animation.py        时域仿真、GIF 动画、关键帧、时间序列
make_compare.py          场景对比图
report_data.py           报告定量数据
diag_discretization.py   离散化收敛性诊断
check_texact.py          闭式解与逐点标准公式校验
plot_style.py            中文字体与绘图风格
figures/                 全部静态图 (fig1-fig6, anim_compare, snap_*, verification_table.txt)
animations/              4 个隧穿时域仿真 GIF
data/                    各场景概率时间序列 (.npz)
```
