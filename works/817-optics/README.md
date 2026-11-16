# 817《光学》× Python 仿真 学习指南

> 一份把「考研光学」和「能跑起来的代码」绑在一起的学习方案。
> 每背一个公式，就让程序把它算一遍；算不出来的地方，就是你的漏洞。

---

## 目录

0. [30 秒上手](#0-30-秒上手)
1. [为什么要用 Python 学光学](#1-为什么要用-python-学光学)
2. [817 考纲全景 × 仿真映射表](#2-817-考纲全景--仿真映射表)
3. [环境搭建](#3-环境搭建)
4. [四个必须会的 Python 工具](#4-四个必须会的-python-工具)
5. [16 周学习路线](#5-16-周学习路线)
6. [分章精讲：公式 → 仿真 → 考点](#6-分章精讲公式--仿真--考点)
7. [三种核心学习方法](#7-三种核心学习方法)
8. [应试技巧](#8-应试技巧)
9. [常见错误清单](#9-常见错误清单)
10. [工程文件清单与扩展](#10-工程文件清单与扩展)
- [附录 A：公式速查](#附录-a公式速查)
- [附录 B：参考书目与在线资源](#附录-b参考书目与在线资源)

---

## 0. 30 秒上手

```powershell
cd "817光学-Python仿真"

# 1) 装依赖（numpy / scipy / matplotlib / sympy，四个库）
pip install -r requirements.txt

# 2) 跑物理自检：79 项公式与仿真互验，全绿说明环境没问题
python selfcheck.py

# 3) 一键跑完全部 12 个仿真实验，图存到 outputs/
python run_all.py

# 4) 只看某一章
python run_all.py d07 d08
```

跑完 `outputs/` 里会出现 12 张图。**先看图，再看第六章对应的小节**，比按顺序读效率高得多。

---

## 1. 为什么要用 Python 学光学

考研复习的三大痛点，仿真恰好都能治：

| 痛点 | 传统做法 | 仿真做法 |
|---|---|---|
| **公式记混** | 反复抄写、靠"感觉" | 让程序算一遍，与课本数值对不上就是记错了 |
| **物理图像模糊** | 盯着一张静态插图想象 | 调参数看曲线怎么变（这就是"参数地图"） |
| **不会估数量级** | 算完了也不知道对不对 | 用数量级是否合理反向检验自己的答案 |
| **抽象概念（相位、频谱、光瞳）** | 死记定义 | 画出来看，反而不用背 |

但要**先说清楚边界**：

- 仿真**不能替代**推导。考研大题考的是"从公式 A 推到结果 B"，程序只能验证结果。
- 仿真**不能替代**做题。它的定位是**校验器**和**直觉来源**。
- 本指南的建议比例：**推导与做题 70%，仿真 30%**。仿真省下来的时间应该还给刷题。

---

## 2. 817 考纲全景 × 仿真映射表

本工程按**中国科学院大学 817《光学》**考纲搭建（[考纲原文](https://admission.ucas.ac.cn/Content/Upload/2025/7/817%20%e5%85%89%e5%ad%a6.pdf)，[整理版](https://m.koolearn.com/kaoyan/20250902/1870285.html)）：

- 总分 **150 分**，考试时间 **180 分钟**，闭卷笔试
- **物理光学约 60%**、**应用光学约 40%**
- 基本概念与理论 60%、综合与实际应用 40%
- 主要题型：**简答题、计算题**
- 参考书：石顺祥等《物理光学与应用光学（第二版）》；郁道银等《工程光学（第二版）》

> 若你的目标院校用的是别的大纲（如北理工、长理工的 817），第一章到第三章内容基本重合，
> 直接按下面的表格对照增删即可，工程代码不用改。

| 考纲条目 | 核心公式 | 对应仿真 | 一定要看到的结论 |
|---|---|---|---|
| 光波特性、频谱 | $E=A\cos(kz-\omega t)$，$\lambda_n=\lambda_0/n$ | `wave.plane_wave` `group_velocity` | 相速度 ≠ 群速度（色散介质） |
| 反射折射、菲涅耳公式 | $r_s,r_p,t_s,t_p$ | `demos/d01` | 正入射 $R=((n_1-n_2)/(n_1+n_2))^2$；$r_s<0$ 即半波损失 |
| 布儒斯特角 | $\tan i_B=n_2/n_1$ | `wave.brewster_angle` | 此处 $r_p=0$，反射光全偏振 |
| 全反射、相移 | $\sin i_C=n_2/n_1$；$\tan\frac{\delta_s}{2}$ | `wave.tir_phase_shifts` | $\delta_p-\delta_s$ 最大约 45°→ 菲涅耳菱体 |
| 偏振态表示 | 琼斯矢量、斯托克斯参量 | `demos/d02` | 波片改偏振态不改光强 |
| 双光束干涉 | $\Delta=d\sin\theta$，$\Delta x=\lambda D/d$ | `demos/d03` | 条纹间距 ∝ λ、∝ D、∝ 1/d |
| 平行平板多光束 | 爱里公式 $T=\frac{1}{1+F\sin^2(\delta/2)}$ | `demos/d04` | $F^*=\pi\sqrt R/(1-R)$；多光束条纹极锐 |
| 光学薄膜 | $R=\left(\frac{n_0n_s-n^2}{n_0n_s+n^2}\right)^2$ | `demos/d05` | 增透条件 $n=\sqrt{n_0n_s}$，$d=\lambda_0/4n$ |
| 干涉仪 | 牛顿环 $r_m=\sqrt{m\lambda R}$；F-P $FSR=\lambda^2/2nd$ | `demos/d06` | 迈克尔逊移 $\lambda/2$ 移一条条纹 |
| 夫琅禾费单缝 | $a\sin\theta=k\lambda$ | `demos/d07` | 中央亮纹半角宽 $\lambda/a$ |
| 圆孔、分辨本领 | $\theta=1.22\lambda/D$ | `diffraction.airy_radius` | 艾里斑，瑞利判据 |
| 光栅 | $d\sin\theta=m\lambda$；$R=mN$；缺级 $d/a=m/k$ | `demos/d07` | 位置由 d 定、锐度由 N 定、包络由 a 定 |
| 菲涅耳衍射 | $I/I_0=4\sin^2(\pi N/2)$，$N=a^2/\lambda z$ | `demos/d08` | $N=1$ 亮 4 倍；波带片 $f_m=a^2/m\lambda$ |
| 直边衍射 | $v=x\sqrt{2/\lambda z}$ | `diffraction.fresnel_edge_intensity` | 阴影边界 $I=I_0/4$，极大 1.37$I_0$ |
| 傅里叶光学 | 后焦面 = 物函数的频谱 | `demos/d09` | CTF 与 OTF 截止频率差 2 倍 |
| 单轴晶体 | $\frac{1}{n_e^2}=\frac{\cos^2\theta}{n_o^2}+\frac{\sin^2\theta}{n_e^2}$ | `demos/d12` | 沿光轴无双折射；方解石走离角 ≈6.2° |
| 波片、偏振棱镜 | $\delta=2\pi|n_o-n_e|d/\lambda$ | `polarization.waveplate_thickness` | 1/4 波片：线偏振→圆偏振 |
| 偏光干涉 | $T=\sin^22\varphi\sin^2(\delta/2)$ | `polarization.polarization_interference_transmission` | $\varphi=0$ 时永远消光 |
| 电光/声光/法拉第 | $V_\pi=\lambda/(2n_o^3r_{63})$；$\sin\theta_B=\lambda/2\Lambda$ | `polarization.pockels_half_wave_voltage` | KDP 纵向 $V_\pi\approx7.5$ kV |
| 折射球面成像 | $n'/l'-n/l=(n'-n)/r$ | `geometrical.refraction_sphere` | 与近轴矩阵结果必须完全一致 |
| 理想光学系统 | 基点基面、双光组组合 | `demos/d10` | 公式和矩阵两条路必须给出同一答案 |
| 光路计算、球差 | $y$- $u$ 递推；实际光线追迹 | `geometrical.paraxial_trace` `refract_sphere_real` | 球差 = 实际交点 − 近轴交点 |
| 光阑 | 物方孔径角 $u_i=(D_i/2)/|B_i|$ | `demos/d11` | 最小者即孔径光阑；其像为入瞳/出瞳 |
| 光学仪器 | $\Gamma_{望远镜}=f_o'/f_e'$；$d=0.61\lambda/NA$ | `instruments.*` | 分辨本领由口径/NA 决定，不由放大率决定 |

---

## 3. 环境搭建

### 3.1 最小环境（推荐）

需要 **Python ≥ 3.9**（本工程在 3.11.5 + numpy 2.2.6 上验证通过）。

```powershell
# 建虚拟环境（强烈建议，避免污染系统 Python）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python selfcheck.py     # 期望输出：全部 79 项自检通过
```

`requirements.txt` 只装四个纯数值库：`numpy`、`scipy`、`matplotlib`、`sympy`。装得快、坑少。

### 3.2 可选增强

| 用途 | 包 | 什么时候值得装 |
|---|---|---|
| 交互式笔记本 | `jupyterlab` | 想边推公式边出图时 |
| 滑块调参 | `ipywidgets` | 做"参数地图"最爽 |
| 三维光场、可缩放图 | `plotly` | 想看二维光场立体图 |
| 动画讲解 | `manim` | 想录视频/讲给别人听 |
| 专业光学库 | `prysm`、`LightPipes`、`diffractio`、`rayoptics` | **学有余力再看**，考研不必依赖 |

> **建议**：前 8 周只用本工程的四个库。过早引入大而全的光学库，会让你在"调库 API"上耗掉本该做题的时间。

### 3.3 中文字体（重要）

matplotlib 默认字体画不出中文，会显示成方框。本工程在 `optics817/plotstyle.py` 里自动挑选可用中文字体（微软雅黑 / 黑体 / 思源黑体 …）。函数末尾有：

```python
use_chinese_font()   # 导入 optics817 时自动执行
```

如果你自己新建绘图脚本，记得 `import optics817` 或显式调用一次。

---

## 4. 四个必须会的 Python 工具

### 4.1 numpy：广播与网格

光学仿真 90% 的工作量是「在一个网格上算一个公式」。

```python
import numpy as np
x = np.linspace(-1e-3, 1e-3, 2000)          # 一维屏坐标
X, Y = np.meshgrid(x, x)                     # 二维网格
r = np.hypot(X, Y)                           # 对每个点求半径（广播）
```

记住三条：
1. **一切用数组，不要写循环** —— 循环慢 100 倍，且容易写错。
2. `np.sinc(x)` 的定义是 $\sin(\pi x)/(\pi x)$，**带 π**！所以 $\sin\beta/\beta = \texttt{np.sinc}(\beta/\pi)$。这是最容易踩的坑。
3. 复数就是光学：`np.abs(U)**2` 得强度，`np.angle(U)` 得相位。

### 4.2 matplotlib：三行出图

```python
import matplotlib; matplotlib.use("Agg")   # 只存图不弹窗，脚本里更快
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
axes[0, 0].plot(x*1e3, I)
axes[0, 0].set_xlabel("屏坐标 x / mm")
fig.savefig("out.png", dpi=140, bbox_inches="tight")
```

### 4.3 sympy：符号推导（第 7.1 节的主角）

用来验证你自己推的解析式，而不是代替你推。

```python
import sympy as sp
n1, n2, i, t = sp.symbols("n1 n2 i t", positive=True)
# 斯涅尔定律 + 菲涅耳 rp，验证布儒斯特角
rp = (n2*sp.cos(i) - n1*sp.cos(t)) / (n2*sp.cos(i) + n1*sp.cos(t))
sol = sp.solve(sp.Eq(n1*sp.sin(i), n2*sp.sin(t)), t)[0]
print(sp.simplify(rp.subs(t, sol)))        # 观察什么条件下为 0
print(sp.solve(sp.tan(i) - n2/n1, i))      # 得出 i_B
```

### 4.4 scipy：特殊函数与 FFT

```python
from scipy.special import j1, fresnel   # 贝塞尔函数、菲涅尔积分
S, C = fresnel(v)          # 注意！scipy 返回的顺序是 (S, C)，别写反
from scipy.fft import fft2, ifft2, fftshift, ifftshift
```

**FFT 是仿真利器**：菲涅耳衍射、夫琅禾费衍射、4f 系统、光栅，全都是一两个 FFT。

---

## 5. 16 周学习路线

假设每周有效学习 12–16 小时。**仿真是配角，每周只占 2–3 小时。**

| 周 | 内容 | 仿真任务 | 本周产出（可检验） |
|---|---|---|---|
| 1 | 第一章：光波、菲涅耳公式 | `python run_all.py d01` | 手推 $R$ 公式并解释两个偏振分量差异 |
| 2 | 布儒斯特角、全反射、偏振态 | `d02` + 用 sympy 验证 | 说清为什么反射光能全偏振 |
| 3 | 第二章：相干性、双光束干涉 | `d03` | 独立算出 3 种装置的条纹间距 |
| 4 | 多光束干涉、F-P | `d04` | 推导精细度与分辨本领 |
| 5 | 光学薄膜 | `d05` | 设计一个双面增透膜方案 |
| 6 | 干涉仪综合 | `d06` | 牛顿环测曲率半径完整解题 |
| 7 | **阶段复习 + 第一次自测** | 重跑 `selfcheck.py` | 错题本第一版 |
| 8 | 第三章：夫琅禾费衍射 | `d07` | 单缝/圆孔/光栅三类题全会 |
| 9 | 菲涅耳衍射、波带片 | `d08` | 半波带法完整推导 |
| 10 | 傅里叶光学 | `d09` | 解释阿贝成像与空间滤波 |
| 11 | 第四章：晶体光学 | `d12` | 会画折射率面、会算波片 |
| 12 | 第五章：电光/声光/法拉第 | `d12` | 会算 $V_\pi$、布喇格角 |
| 13 | 第七、八章：几何光学、理想系统 | `d10` | 图解法与解析法都能做 |
| 14 | 第九章：像差与光阑 | `d11` | 光阑判定流程能背下来 |
| 15 | 第十章：光学仪器 + 吸收色散散射 | `instruments` | 显微镜/望远镜全参数题 |
| 16 | **全真模拟 + 查漏** | 重跑全部 demo | 每章能自己出 3 道题 |

**每周固定动作**：
1. 先通读教材该章，把公式自己推一遍（不看书）；
2. 跑对应 demo，**先猜曲线形状再看图**；
3. 做课后题 + 真题，错的题记进错题本；
4. 把错题涉及的量用仿真算一遍，确认自己的答案错在哪一步。

---

## 6. 分章精讲：公式 → 仿真 → 考点

### 6.1 第一章 光的电磁理论基础

**考点**：光波表示、频谱、菲涅耳公式、布儒斯特角、全反射、偏振态。

**必背公式**

$$r_s=\frac{n_1\cos i-n_2\cos t}{n_1\cos i+n_2\cos t},\qquad
r_p=\frac{n_2\cos i-n_1\cos t}{n_2\cos i+n_1\cos t}$$

$$R_s=|r_s|^2,\quad R_p=|r_p|^2,\quad \tan i_B=\frac{n_2}{n_1},\quad \sin i_C=\frac{n_2}{n_1}\ (n_1>n_2)$$

**跑这个**：`python demos/d01_fresnel.py`

**应该看到**
- 正入射 $R=0.04$（空气→$n=1.5$ 玻璃），所以未镀膜镜片双面反射损失约 8%；
- $r_p$ 在某角降为 0 —— 那就是布儒斯特角；此处反射光是**完全线偏振**的；
- 全反射区 $R\equiv1$，但**相位在变**，且 $\delta_p\neq\delta_s$，最大差约 45°；
- 部分反射区 $r_s$ 恒有 π 相位跃变，$r_p$ 在布儒斯特角处从 0 翻到 π（穿过零点）。

**易错点**
- "半波损失"只对**反射光**、且是**光疏→光密**时才有（$n_1<n_2$）；
- $r_p$ 与 $r_s$ 的定义里 $\cos i$ 与 $\cos t$ 谁配 $n_1$ 谁配 $n_2$，不同教材符号约定不同，**做题时先写出你用的约定**；
- 全反射时折射角是虚数，不能写 $\sin t>1$ 就完事，要说明"折射波沿界面传播、振幅指数衰减（隐失波）"。

---

### 6.2 第二章 光的干涉

**考点**：相干条件、双光束、多光束、薄膜、干涉仪。

**必背公式**

$$\Delta x=\frac{\lambda D}{d}\quad(\text{双缝}),\qquad
T=\frac{1}{1+F\sin^2(\delta/2)},\ F=\frac{4R}{(1-R)^2}$$

$$F^*=\frac{\pi\sqrt R}{1-R},\qquad FSR=\frac{\lambda^2}{2nd},\qquad
r_m=\sqrt{m\lambda R}\ (\text{牛顿环暗环})$$

**跑这个**：`d03` `d04` `d05` `d06`

**应该看到**
- 双缝条纹间距与 λ、D 成正比、与 d 成反比；单缝包络会"削掉"某些级次；
- 多光束干涉条纹随 R 增大迅速变尖，$T_{\min}/T_{\max}=1/(1+F)$；
- 1/4 波长增透膜在设计波长处 $R=0$，偏离 50 nm 就明显退化；
- 牛顿环中心是**暗**斑（反射光），亮环半径 $\sqrt{(m+\tfrac12)\lambda R}$。

**易错点**
- 牛顿环反射光中心暗、透射光中心亮，**别写反**；
- 迈克尔逊干涉仪"移动 $\lambda/2$ 条纹过一条"，$d$ 与条纹移动数 $N$ 关系是 $d=N\lambda/2$；
- 多光束干涉的相位差是 $\delta=\frac{4\pi}{\lambda}nd\cos\theta$（有**两倍**）；
- 薄膜干涉要同时考虑**两个界面的半波损失是否抵消**。

---

### 6.3 第三章 光的衍射

**考点**：夫琅禾费（单缝、圆孔、多缝、巴俾涅）、菲涅耳（圆孔、直边）、光栅、波带片。

**必背公式**

$$a\sin\theta=k\lambda,\qquad \theta_{\text{中央}}=\frac{\lambda}{a},\qquad
\theta_{\text{艾里}}=1.22\frac{\lambda}{D}$$

$$d\sin\theta=m\lambda,\qquad R=\frac{\lambda}{\Delta\lambda}=mN,\qquad
\text{缺级}:\ \frac{d}{a}=\frac{m}{k}$$

$$N=\frac{a^2}{\lambda z},\qquad \frac{I}{I_0}=4\sin^2\frac{\pi N}{2},\qquad
f_m=\frac{a^2}{m\lambda}$$

**跑这个**：`d07` `d08`

**应该看到**
- 单缝缝越窄，中央亮纹越宽（衍射越显著）；
- 圆孔第一个暗环在 $u=3.832$，对应角半径 $1.22\lambda/D$；
- 多缝条纹位置由 $d$ 定、尖锐程度由 $N$ 定、强度包络由 $a$ 定；
- 菲涅耳圆孔轴上强度随距离振荡：$N=1$ 亮 4 倍，$N=2$ 全暗；
- 直边阴影边界恰好 $I=I_0/4$，照明区第一极大 $1.37I_0$。

**易错点**
- 光栅题里 $d$ 是**光栅常数**（相邻缝距），$a$ 是**缝宽**，两者别混；
- 分辨本领 $R=mN$ 中的 $N$ 是**参与衍射的总缝数**，不是刻线密度；
- 菲涅耳半波带：$N$ 可以是小数，"奇数亮、偶数暗"只对整数成立；
- 巴俾涅原理说的是**振幅**互补相加等于自由场，不是强度相减。

---

### 6.4 第三章第 5 节 傅里叶光学

**考点**：频谱、阿贝成像、空间滤波、传递函数。

**必背结论**

$$\text{谱面坐标}\ x_f=\lambda f\cdot f_x,\qquad
\text{截止频率}\ f_c=\frac{D}{2\lambda f},\qquad
OTF\ \text{截止}=2f_c$$

**跑这个**：`python demos/d09_fourier_optics.py`

**应该看到**
- 透镜后焦面上出现的是物的**傅里叶频谱**（低频在中心）；
- 挡掉高频 → 图像变模糊；只留高频 → 勾边；
- 相干照明用 CTF（0/1 型），非相干照明用 OTF（三角形/圆型），后者截止频率是前者的 2 倍。

**易错点**
- 物面空间频率与谱面**坐标**不是一回事，换算要乘 $\lambda f$；
- 相干成像系统对**振幅**线性，非相干对**强度**线性——卷积的对象不同。

---

### 6.5 第四、五章 各向异性介质与感应双折射

**考点**：单轴晶体、双折射、波片、偏振棱镜、偏光干涉、旋光、电光、声光、法拉第。

**必背公式**

$$\frac{1}{n_e^2(\theta)}=\frac{\cos^2\theta}{n_o^2}+\frac{\sin^2\theta}{n_e^2},\qquad
\delta=\frac{2\pi}{\lambda}|n_o-n_e|d$$

$$T=\sin^2 2\varphi\cdot\sin^2\frac{\delta}{2}\ (\text{正交偏振器}),\qquad
V_\pi=\frac{\lambda}{2n_o^3r_{63}},\qquad \sin\theta_B=\frac{\lambda}{2\Lambda}$$

**跑这个**：`python demos/d12_crystal_optics.py`

**应该看到**
- 沿光轴（$\theta=0$）传播时 $n_e(\theta)=n_o$，**没有双折射**；
- 方解石（负晶体）e 光走离角在 45° 附近最大，约 6.2°；
- 波片只改变偏振态，正交偏振器 + 波片才把相位变成强度；
- KDP 纵向半波电压约 7.5 kV（550 nm）。

**易错点**
- 正负晶体判据是 $n_e$ 与 $n_o$ 谁大，**石英是正晶体**（$n_e>n_o$）；
- "1/4 波片"是对**特定波长**成立的，换波长就变成其他延迟量；
- 偏光干涉 $\varphi=0$ 或 90° 时无论相位延迟多少都消光（这是常考的"陷阱"选项）；
- 自然旋光与法拉第旋光的**方向性**不同：法拉第旋转方向由磁场定，与光传播方向无关（光隔离器的原理）。

---

### 6.6 第七、八章 几何光学与理想光学系统

**考点**：符号规则、单球面、平板棱镜、基点基面、双光组组合。

**必背公式**

$$\frac{n'}{l'}-\frac{n}{l}=\frac{n'-n}{r},\qquad \beta=\frac{nl'}{n'l},\qquad
\frac{1}{l'}-\frac{1}{l}=\frac{1}{f'},\qquad xx'=ff'$$

$$\Delta=d-f_1'+f_2,\qquad f'=-\frac{f_1'f_2'}{\Delta},\qquad
l_F'=f'\left(1-\frac{d}{f_1'}\right)$$

**跑这个**：`python demos/d10_geometrical.py`

**应该看到**
- 单球面 $l=-300,r=100,1\to1.5$ 时 $l'=900$、$\beta=-2$；
- 双光组组合公式与近轴矩阵给出的结果**逐位相同**（我把它做成了自检项）；
- 物在 2F 处像在 2F'，$\beta=-1$。

**易错点**
- 符号规则必须先声明：$l$、$y$、$u$ 的正负方向；
- 双光组组合里 $f_2$ 是**物方**焦距，与 $f_2'$ 差一个负号，这是最常见的翻车点；
- 当 $d=f_1'+f_2$ 时 $\Delta=0$，系统**无焦**（望远镜），不能直接套焦距公式。

---

### 6.7 第九章 像差与光路计算、光阑

**考点**：$y$-$u$ 递推、子午面实际光线、球差、孔径光阑/视场光阑/光瞳/窗。

**核心判据**

$$u_i=\frac{D_i/2}{|B_i|}\ \xrightarrow{\ \min\ }\ \text{孔径光阑}$$

其中 $B_i$ 是「物面 → 第 $i$ 个光阑所在面」的累计近轴矩阵的 $(0,1)$ 元素。

**跑这个**：`python demos/d11_aperture_stop.py`

**应该看到**
- 各光阑按物方孔径角排序，最小者就是孔径光阑；
- 入射光瞳 = 孔径光阑经**前面**系统的像，出射光瞳 = 经**后面**系统的像；
- 球差曲线：边缘光线交点比近轴焦点更近（正透镜球差为负）。

**易错点**
- 入射光瞳是**虚像**时位置可以是负的（在物面右侧），不要以为算错了；
- 视场光阑用**主光线**（过入射光瞳中心）判定，不要用边缘光线；
- 近轴光路计算和实际光线追迹是两套算法，球差就是两者之差——这个理解比背公式更重要。

---

### 6.8 第十章 光学仪器

**考点**：眼睛、放大镜、显微镜、望远镜。

**必背公式**

$$\Gamma_{\text{放大镜}}=\frac{250}{f},\qquad
\Gamma_{\text{显微镜}}=\left|\beta_{obj}\right|\cdot\frac{250}{f_e'},\qquad
\Gamma_{\text{望远镜}}=\frac{f_o'}{f_e'}$$

$$d_{\min}=\frac{0.61\lambda}{NA},\qquad \theta_{\min}=1.22\frac{\lambda}{D}$$

**跑这个**（无图，直接算）：

```python
from optics817 import instruments as ins
print(ins.microscope_resolution(550e-9, 0.9))         # 显微镜最小分辨距离
print(ins.telescope_resolution_arcsec(550e-9, 0.1))   # 望远镜最小分辨角(角秒)
print(ins.telescope_magnification(1.0, 0.02))         # 望远镜放大率
```

**易错点**
- 显微镜**放大率与分辨本领无关**：NA 决定能分辨多细，放大率只决定看起来多大；
- 望远镜物镜口径决定分辨本领，放大率只决定出瞳直径匹配人眼；
- 明视距离是 **250 mm**，别记成 25 cm 以外的数。

---

### 6.9 第六章 光的吸收、色散、散射

考纲要求"了解"，做简答题准备即可：

- **吸收**：$I=I_0e^{-\alpha l}$（朗伯定律），$\alpha$ 与波长有关 → 选择吸收；
- **色散**：$n=n(\lambda)$，正常色散 $dn/d\lambda<0$；用 $n=A+\frac{B}{\lambda^2}+\frac{C}{\lambda^4}$；
- **散射**：瑞利散射 $I\propto1/\lambda^4$（天空蓝、夕阳红）；米氏散射（颗粒尺寸接近波长）；拉曼散射（频率改变）。

---

## 7. 三种核心学习方法

### 7.1 方法一：公式—仿真互验（最重要）

`selfcheck.py` 里有 **79 项**断言，每一项都是"课本公式 vs 数值计算"的正面对撞。它就是你复习时的**裁判**。

```python
# 例：验证爱里公式的两个极值
r = 0.5
F = 4 * r**2 / (1 - r**2) ** 2
assert np.isclose(itf.airy_transmission(0.0, r), 1.0)          # Tmax = 1
assert np.isclose(itf.airy_transmission(np.pi, r), 1/(1+F))    # Tmin = 1/(1+F)
```

**你要养成的习惯**：每学完一节，自己往 `selfcheck.py` 里加 3–5 条断言。加不出来的地方，就是你没学懂的地方。

一条好的自检断言长这样：

```python
check("光栅方程 d sin(theta) = m lambda",
      d * np.sin(dif.grating_angle(m, 550e-9, d)), m * 550e-9)
```

它把公式的**两边分别用不同代码路径**算出来，任何一边写错都会报错。

### 7.2 方法二：参数地图

不要只算一组数。把参数扫一遍，看**趋势**和**临界行为**：

```python
import numpy as np
from optics817 import interference as itf

# 缝宽 a 从 0.02 mm 扫到 0.5 mm，看条纹可见度如何变化
for a in np.linspace(0.02e-3, 0.5e-3, 10):
    I = itf.double_slit_intensity(np.linspace(-6e-3, 6e-3, 4001),
                                 600e-9, 0.5e-3, a=a, z=1.0)
    print(f"a={a*1e3:.3f} mm  可见度 V={(I.max()-I.min())/(I.max()+I.min()):.3f}")
```

**考场上你没法跑程序，但趋势已经在你脑子里了**：
"缝越宽、包络越窄、可见度越低" —— 这句话能帮你秒判选择题。

### 7.3 方法三：错题反演

错题不要只抄一遍答案，要做**反演**：

1. 写下你的错误答案；
2. 用仿真算出正确答案；
3. **找出你的错误对应哪个物理量的偏差**（少乘 2？用了 $\sin$ 而不是 $\tan$？漏了半波损失？）；
4. 把这条经验写成一句话，加进 `selfcheck.py`。

例如，如果你做牛顿环时忘了半波损失：

```python
# 错误模型：I = cos²(πr²/(λR))  →  中心是亮的（错！）
# 正确模型：I = sin²(πr²/(λR))  →  中心是暗的
check("牛顿环中心必须为暗斑（反射光）",
      itf.newton_rings_intensity(0.0, 600e-9, 1.0), 0.0)
```

**这条断言会永远替你记住这个坑。**

---

## 8. 应试技巧

### 8.1 时间分配（180 分钟 / 150 分）

| 阶段 | 时间 | 做什么 |
|---|---|---|
| 第 1 遍 | 5 min | 通览全卷，把题按"会/半会/不会"标记 |
| 第 2 遍 | 120 min | 先做会的，简答题先写定义和公式 |
| 第 3 遍 | 35 min | 攻克半会的，写出关键步骤拿步骤分 |
| 检查 | 20 min | 量纲、数量级、单位、正负号 |

### 8.2 简答题模板

**问"为什么"**：现象 → 原理（写公式）→ 结论。
> 例：为什么反射光在布儒斯特角完全偏振？
> 答：自然光可分解为 $s$、$p$ 两个分量。由菲涅耳公式 $r_p=(n_2\cos i-n_1\cos t)/(n_2\cos i+n_1\cos t)$，当 $i+t=90°$ 时分子为零，即 $r_p=0$，故反射光中只剩 $s$ 分量，成为完全线偏振光。

**问"区别与联系"**：列表对比 + 一句话总结。
> 例：菲涅耳衍射与夫琅禾费衍射的区别 → 从"光源/观察屏是否在有限远""能否用半波带法""数学上是积分还是变换"三点对比。

### 8.3 计算题模板（万能的五步）

1. **画图**，标出所有已知量和未知量；
2. **写公式**（原式，不要直接代数）；
3. **统一单位**（全部换 SI，或全部用 mm）；
4. **代入计算**，保留 4 位有效数字；
5. **检验**：量纲对不对？数量级合不合理？（比如可见光波长必然是几百 nm 量级）

### 8.4 单位与有效数字

- 波长：$550\,\text{nm}=5.5\times10^{-7}\,\text{m}$；换算时**先化成米**再代入公式，最不容易错；
- 角度：公式里的 $\sin\theta\approx\theta$ 只在**弧度**下成立；
- 答案一般保留 **4 位有效数字**；角度用度或弧度都写清单位。

### 8.5 高频考点清单（考前一周只看这个）

1. 菲涅耳公式 + 布儒斯特角 + 全反射相移
2. 杨氏双缝 / 薄膜干涉 / 牛顿环 的条纹条件
3. 多光束干涉爱里公式 + F-P 分辨本领
4. 增透膜设计（$n=\sqrt{n_0n_s}$、$d=\lambda_0/4n$）
5. 单缝 / 圆孔 / 光栅 三件套 + 缺级 + 分辨本领
6. 菲涅耳半波带法（$N$ 为奇数偶数）
7. 单轴晶体双折射 + 波片设计
8. 偏光干涉 $T=\sin^22\varphi\sin^2(\delta/2)$
9. 单球面近轴成像 + 双光组组合
10. 孔径光阑 / 入射光瞳 / 出射光瞳的判定流程

---

## 9. 常见错误清单

**第一章**
1. 把 $R=|r|$ 当成反射率（应为 $|r|^2$）
2. 忘记正入射时 $R_s=R_p$、斜入射时 $R_s>R_p$
3. 认为全反射没有波进入第二介质（有隐失波）
4. 半波损失适用条件搞错（只对反射光、光疏→光密）

**第二章**
5. 牛顿环反射光中心记成亮斑
6. 多光束相位差漏掉因子 2（应为 $4\pi nd\cos\theta/\lambda$）
7. 迈克尔逊 $d$ 与条纹数的关系少乘 $1/2$
8. 增透膜条件写成 $n=n_0n_s$（应为平方根）
9. 条纹可见度公式写成 $I_{\max}/I_{\min}$

**第三章**
10. `np.sinc` 的定义里自带 π，直接传 $\beta$ 会错
11. 光栅的 $d$ 与 $a$ 混用
12. 分辨本领 $R=mN$ 中的 $N$ 用成刻线密度
13. 艾里斑角半径系数写成 1.0（应为 1.22）
14. 菲涅耳圆孔轴上强度直接写 $I_0$（实际随 $N$ 振荡）
15. 单缝衍射极小条件写成 $a\sin\theta=(k+\tfrac12)\lambda$

**第四章、第五章**
16. 正负晶体的判据记反
17. 认为沿光轴也有双折射
18. 波片厚度公式漏掉 $|n_o-n_e|$
19. 偏光干涉中 $\varphi=0$ 时以为仍有调制
20. 法拉第旋转方向与光传播方向有关（实际无关）

**第七~九章**
21. $1/l'-1/l=1/f'$ 的符号写错
22. 双光组组合里 $f_2$ 与 $f_2'$ 混用
23. 入射光瞳位置算成负的就以为错了（虚像很正常）
24. 用边缘光线而不是主光线判定视场光阑
25. 球差正负号记反

**通用**
26. 小角近似 $\sin\theta\approx\theta$ 在度数下使用
27. nm 没换算成 m 直接代入
28. 结果不检查量纲
29. 复数振幅直接相加却忘了取模平方
30. 只算数值不写公式，步骤分全丢

---

## 10. 工程文件清单与扩展

```
817光学-Python仿真/
├── README.md                  ← 本文档（学习指南）
├── 公式速查卡.md               ← 可打印的一页公式表
├── requirements.txt
├── selfcheck.py               ← 79 项公式自检（最重要！请自己往里加）
├── run_all.py                 ← 一键跑全部实验
├── optics817/                 ← 仿真库（按考纲分模块）
│   ├── wave.py                ← 第一章：菲涅耳、全反射、琼斯矩阵、多层膜
│   ├── interference.py        ← 第二章：双光束、多光束、薄膜、干涉仪
│   ├── diffraction.py         ← 第三章：夫琅禾费、菲涅耳、光栅、波带片
│   ├── fourier_optics.py      ← 第三章第 5 节：传播、4f、CTF/OTF
│   ├── polarization.py        ← 第四、五章：晶体、波片、电光、声光
│   ├── geometrical.py         ← 第七~九章：近轴矩阵、光路、光阑、球差
│   ├── instruments.py         ← 第十章：眼睛、显微镜、望远镜
│   └── plotstyle.py           ← 中文字体与出图工具
├── demos/                     ← 12 个分章实验（每个都能单独运行）
└── outputs/                   ← 生成的图
```

### 怎么扩展成你自己的版本

1. **加断言**：`selfcheck.py` 里按章节加，把自己错的每一道题变成一条断言；
2. **加参数扫描**：仿照 7.2 节，把每章的关键参数扫一遍，记录趋势；
3. **加真题**：把真题里的数值直接代进 `optics817` 的函数，与标准答案对照；
4. **改成 Notebook**：`jupyter lab`，把每个 demo 拆成单元格，方便边改边看；
5. **进阶库**：学有余力时试 `prysm`（物理光学全能）或 `rayoptics`（几何光学设计）。

> **最后一句提醒**：这套工程最大的价值不是那 12 张图，而是 `selfcheck.py` 这个习惯
> —— **每一个你背下来的公式，都应该有一条能在半分钟内跑完的验证。**

---

## 附录 A：公式速查

| 名称 | 公式 |
|---|---|
| 介质中波长/相速 | $\lambda_n=\lambda_0/n$，$v=c/n$ |
| 菲涅耳振幅系数 | $r_s=\dfrac{n_1\cos i-n_2\cos t}{n_1\cos i+n_2\cos t}$，$r_p=\dfrac{n_2\cos i-n_1\cos t}{n_2\cos i+n_1\cos t}$ |
| 正入射反射率 | $R=\left(\dfrac{n_1-n_2}{n_1+n_2}\right)^2$ |
| 布儒斯特角 | $\tan i_B=n_2/n_1$ |
| 临界角 | $\sin i_C=n_2/n_1$ |
| 全反射相移 | $\tan\dfrac{\delta_s}{2}=-\dfrac{\sqrt{\sin^2i-n^2}}{\cos i}$，$\tan\dfrac{\delta_p}{2}=-\dfrac{\sqrt{\sin^2i-n^2}}{n^2\cos i}$，$n=n_2/n_1$ |
| 马吕斯定律 | $I=I_0\cos^2\theta$ |
| 双缝条纹间距 | $\Delta x=\lambda D/d$ |
| 爱里公式 | $T=\dfrac{1}{1+F\sin^2(\delta/2)}$，$F=\dfrac{4R}{(1-R)^2}$ |
| 精细度 | $F^*=\dfrac{\pi\sqrt R}{1-R}$，$\dfrac{\lambda}{\Delta\lambda}=mF^*$ |
| F-P 自由光谱范围 | $FSR=\dfrac{\lambda^2}{2nd}$ |
| 单层增透膜 | $n=\sqrt{n_0n_s}$，$d=\dfrac{\lambda_0}{4n}$ |
| 牛顿环 | 暗环 $r_m=\sqrt{m\lambda R}$，亮环 $r_m=\sqrt{(m+\frac12)\lambda R}$ |
| 劈尖条纹间距 | $\Delta x=\dfrac{\lambda}{2n\alpha}$ |
| 单缝衍射 | $a\sin\theta=k\lambda$（暗），中央半角宽 $\lambda/a$ |
| 圆孔衍射 | 艾里斑角半径 $1.22\lambda/D$ |
| 光栅方程 | $d\sin\theta=m\lambda$；缺级 $d/a=m/k$ |
| 光栅分辨本领 | $R=\lambda/\Delta\lambda=mN$ |
| 菲涅耳数 | $N=a^2/(\lambda z)$；$I/I_0=4\sin^2(\pi N/2)$ |
| 波带片焦距 | $f_m=a^2/(m\lambda)$，$m$ 为奇数 |
| 直边衍射 | $v=x\sqrt{2/(\lambda z)}$；边界 $I=I_0/4$ |
| 单轴晶体 e 光 | $\dfrac{1}{n_e^2}=\dfrac{\cos^2\theta}{n_o^2}+\dfrac{\sin^2\theta}{n_e^2}$ |
| 波片相位延迟 | $\delta=\dfrac{2\pi}{\lambda}|n_o-n_e|d$ |
| 偏光干涉 | $T=\sin^22\varphi\sin^2(\delta/2)$ |
| 电光半波电压 | $V_\pi=\dfrac{\lambda}{2n_o^3r_{63}}$ |
| 声光布喇格 | $\sin\theta_B=\dfrac{\lambda}{2\Lambda}=\dfrac{\lambda f}{2v}$ |
| 法拉第效应 | $\theta=VBd$ |
| 单球面成像 | $\dfrac{n'}{l'}-\dfrac{n}{l}=\dfrac{n'-n}{r}$，$\beta=\dfrac{nl'}{n'l}$ |
| 高斯公式 | $\dfrac{1}{l'}-\dfrac{1}{l}=\dfrac{1}{f'}$，$\dfrac{1}{v}+\dfrac{1}{u}=\dfrac{1}{f}$ |
| 牛顿公式 | $xx'=ff'$ |
| 双光组组合 | $\Delta=d-f_1'+f_2$，$f'=-\dfrac{f_1'f_2'}{\Delta}$ |
| 显微镜 | $\Gamma=\left|\beta_{obj}\right|\dfrac{250}{f_e'}$，$d_{\min}=\dfrac{0.61\lambda}{NA}$ |
| 望远镜 | $\Gamma=\dfrac{f_o'}{f_e'}$，$\theta_{\min}=1.22\dfrac{\lambda}{D}$ |

---

## 附录 B：参考书目与在线资源

**指定参考书**
1. 石顺祥、王学恩、刘劲松，《物理光学与应用光学（第二版）》，西安电子科技大学出版社，2008
2. 郁道银、谈恒英，《工程光学（第二版）》，机械工业出版社，2006

**考纲来源**
- [中国科学院大学硕士研究生入学考试《光学》考试大纲（817）](https://admission.ucas.ac.cn/Content/Upload/2025/7/817%20%e5%85%89%e5%ad%a6.pdf)
- [817 光学考研大纲整理版（新东方在线）](https://m.koolearn.com/kaoyan/20250902/1870285.html)

**Python 资源**
- NumPy 官方教程：<https://numpy.org/doc/stable/user/quickstart.html>
- Matplotlib 图库：<https://matplotlib.org/stable/gallery/index.html>
- SciPy 特殊函数：<https://docs.scipy.org/doc/scipy/reference/special.html>
- SymPy 符号计算：<https://docs.sympy.org/latest/tutorials/intro-tutorial/index.html>

**进阶光学仿真库（选学）**
- `prysm`：物理光学、偏振、传播，功能最全
- `LightPipes`：波动光学传播，接口极简
- `diffractio`：衍射/干涉/偏振专用，含大量案例
- `rayoptics` / `popoff`：几何光学系统设计

---

*本工程在 Windows + Python 3.11.5 + numpy 2.2.6 环境验证：`selfcheck.py` 全部 79 项通过，12 个 demo 全部正常出图。*
