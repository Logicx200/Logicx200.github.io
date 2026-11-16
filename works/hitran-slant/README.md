# HITRAN2020 大气斜程红外透过率（H₂O / CO₂ / CH₄）

**场景**：平台高度 8 km，地面水平距离 20 km → 斜程 `s = √(20²+8²) = 21.54 km`（天顶角 68.2°）。

## 1. 数据与方法

| 项目 | 设定 |
|---|---|
| 谱线数据 | HITRAN2020（hitran.org `/lbl/api` 下载，2026-11 取数），H₂O / CO₂ / CH₄ 全部同位素分子，475–5025 cm⁻¹，共 825 475 条谱线 |
| 谱线参数 | ν₀, S(296 K), A, γ_air, γ_self, E″, n_air, δ_air |
| 线型 | Voigt（多普勒 + 洛伦兹），含气压频移、线强温度修正（TIPS 配分函数）与洛伦兹半宽温度修正 |
| 同位素 | 按 HITRAN 天然丰度加权（σ 为母体分子每分子截面） |
| 截断 | 线翼按线强取 25 / 12 / 6 cm⁻¹；弱线用 5 倍粗网格 + 插值加速 |
| 大气 | US Standard Atmosphere 1976：T = 288.15 − 6.5z K，p = 1013.25(T/288.15)^5.25588 hPa |
| 水汽 | 地面 7.5 g/m³，标高 2 km（ρ = 7.5·e^(−z/2) g/m³），斜程可降水量 ≈ 40 mm |
| CO₂ | 415 ppmv（均匀混合） |
| CH₄ | 1.9 ppmv（均匀混合） |
| 路径分层 | 24 层，地面附近加密（z = 8u^1.5 km），每层取中点 T、p、数密度 |
| 光谱网格 | 主谱 500–5000 cm⁻¹，步长 0.01 cm⁻¹（45 万点）；8–14 μm 窗口 0.002 cm⁻¹；3–5 μm 窗口 0.005 cm⁻¹ |
| 计算 | τ(ν) = Σ_层 σ(ν;T,p)·n·Δs，T(ν) = exp(−τ) |

> 注：仅包含三种气体的**谱线吸收**，未含水汽连续吸收（MT_CKD）与气溶胶/散射；因此 8–14 μm
> 窗口的透过率略高于真实大气（实际夏季湿大气约低 10–20%）。HITRAN 返回的 CO₂ 数据中含 2901 条
> 同位素号为 0 的极弱线（S ≤ 1.4×10⁻²⁵），对结果无影响，已剔除。

## 2. 主要结果

全红外（2–20 μm）斜程平均透过率：

| 波段 (μm) | 波数 (cm⁻¹) | T 总 | T(H₂O) | T(CO₂) | T(CH₄) |
|---|---|---|---|---|---|
| 2.0–2.5 | 4000–5000 | 0.726 | 0.828 | 0.931 | 0.951 |
| 2.5–3.0 | 3333–4000 | 0.018 | 0.018 | 0.672 | 0.997 |
| 3.0–4.0 | 2500–3333 | 0.562 | 0.619 | 0.999 | 0.888 |
| 4.0–5.0 | 2000–2500 | 0.497 | 0.810 | 0.654 | 0.999 |
| 5.0–6.0 | 1667–2000 | 0.027 | 0.027 | 0.979 | 1.000 |
| 6.0–8.0 | 1250–1667 | 0.022 | 0.048 | 1.000 | 0.860 |
| 8.0–10.0 | 1000–1250 | 0.762 | 0.809 | 0.976 | 0.962 |
| 10.0–12.0 | 833–1000 | 0.895 | 0.918 | 0.975 | 1.000 |
| 12.0–14.0 | 714–833 | 0.452 | 0.744 | 0.590 | 1.000 |
| 14.0–16.0 | 625–714 | 0.000 | 0.374 | 0.000 | 1.000 |
| 16.0–20.0 | 500–625 | 0.032 | 0.089 | 0.631 | 1.000 |

- **8–14 μm 长波红外窗口**平均 T ≈ 0.73，10–12 μm 最透明（T ≈ 0.90）；
- **6.3 μm（H₂O）**、**15 μm / 4.3 μm（CO₂）**、**2.7 μm（H₂O）** 在 21.5 km 斜程上完全饱和（T ≈ 0）；
- **3.3 μm（CH₄）**与 **7.7 μm（CH₄）** 只有部分吸收（窗口处 T ≈ 0.86–0.89），可用于 CH₄ 探测；
- 20 km 量级斜程上，水汽是最主要的红外吸收气体，8–14 μm 窗口内主要由 H₂O 谱线翼与弱线贡献。

## 3. 文件

| 文件 | 说明 |
|---|---|
| `figures/slant_transmittance_HITRAN2020.png/.pdf` | 总图：(a) 2–20 μm 全波段；(b) 8–14 μm 窗口；(c) 3–5 μm |
| `figures/band1_2-3um_SWIR.png/.pdf` | 分波段图①：2–3 μm（每组两张子图：总透过率 + 分气体） |
| `figures/band2_3-5um_MWIR.png/.pdf` | 分波段图②：3–5 μm |
| `figures/band3_5-8um.png/.pdf` | 分波段图③：5–8 μm |
| `figures/band4_8-14um_LWIR.png/.pdf` | 分波段图④：8–14 μm |
| `figures/band5_14-20um.png/.pdf` | 分波段图⑤：14–20 μm |
| `figures/hitran2020_line_sticks.png/.pdf` | HITRAN2020 三种气体谱线强度分布 |
| `output/slant_transmittance_500-5000cm-1.csv` | 波数/波长、T(H₂O)、T(CO₂)、T(CH₄)、T(总)、τ(总)，步长 0.05 cm⁻¹（9 万行） |
| `output/band_mean_transmittance.csv` | 分波段平均透过率表 |
| `output/path_layers.csv` | 24 层大气参数与斜程长度 |
| `slant_spectrum.npz` | 主谱原始数组（0.01 cm⁻¹） |
| `slant_zoom_8_14.npz` / `slant_zoom_3_5.npz` | 窗口高分辨率谱 |
| `slant_band_2_3um.npz` / `slant_band_5_8um.npz` / `slant_band_14_20um.npz` | 分波段高分辨率谱 |
| `hapi.py`, `refetch_serial.py` | HITRAN 数据下载（HAPI + 串行校验） |
| `parse_lines.py`, `lbl.py`, `atmo.py`, `run_calc.py` | 解析 / 逐线计算 / 大气 / 主程序 |
| `make_figures.py`, `make_band_figures.py`, `export_data.py` | 总图、分波段图、数据导出 |

分波段平均透过率（对波长积分平均）：2–3 μm 0.366、3–5 μm 0.554、5–8 μm 0.026、
8–14 μm 0.667、14–20 μm 0.022。

## 4. 复现

```bash
python refetch_serial.py      # 下载 HITRAN2020 谱线（串行+校验，约 10 min）
python parse_lines.py         # 解析为 npz
python run_calc.py --gmin 500 --gmax 5000 --step 0.01 --out slant_spectrum
python run_calc.py --gmin 700 --gmax 1250 --step 0.002 --out slant_zoom_8_14
python run_calc.py --gmin 2000 --gmax 3333 --step 0.005 --out slant_zoom_3_5
python make_figures.py
python export_data.py
```

数值验证：本程序逐线结果与 HAPI `absorptionCoefficient_Voigt` 在 1000–1010 cm⁻¹
（H₂O，296 K，1 atm）线心处一致（差异 < 3%，源于网格取样）。
