# -*- coding: utf-8 -*-
"""
irrecog.params —— 模型唯一参数源（机器可读的真值源）

设计原则
--------
1. 每个参数都带 ``basis`` 字段，取值只能属于四类，禁止"无出处数值"：

   =====  ==========================================================
   SYS    软件实测：从 XGGDCOSSim2 安装目录的配置/模型文件解析得到
   LIT    文献：给出文献编号（见 ``05_参数依据/参数依据说明.md``）
   DER    推导：由其他已登记参数按物理关系推出，并给出公式
   SET    设定：无直接出处但工程合理；必须写明"为什么合理 + 如何被实测替换"
   =====  ==========================================================

2. 本文件是唯一真值源；``05_参数依据/参数依据登记表.csv`` 由 :func:`registry_rows`
   自动导出，报告与图件只允许引用这里的值。

3. **任何"拍脑袋"系数都不得进入本文件**。若后续需要新增经验系数，必须先登记并说明
   其不确定度方向，否则视为建模缺陷。
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# 物理常数（CODATA 2018 / SI）
# --------------------------------------------------------------------------- #
H_PLANCK = 6.62607015e-34   # J·s
C_LIGHT = 2.99792458e8      # m/s
K_BOLTZ = 1.380649e-23      # J/K

# 标准大气与地球几何（ISO 2533:1975；WGS-84 平均半径）——公式登记见 06_校验/公式校准报告.md
R_EARTH_KM = 6371.0         # 地球平均半径 km（斜程几何用，不含折射）
G_ACC = 9.80665             # 标准重力加速度 m/s²
M_AIR = 0.0289644           # 干空气摩尔质量 kg/mol
R_GAS = 8.314462618         # 通用气体常数 J/(mol·K)
H_RAYLEIGH_KM = 8.0         # Rayleigh 散射标高 km（6S 口径：垂直光学厚度 0.008735·λ^-4.08 除以该标高得地面消光系数）
T_REF_WEIGHT_K = 293.15     # 波段对比度加权的参考温度 K（= 背景 20 ℃，由场景背景温度覆盖）

# --------------------------------------------------------------------------- #
# 波段定义（软件实测：模型 Config.ini 的波段字段）
# --------------------------------------------------------------------------- #
BANDS: Dict[str, dict] = {
    "MWIR": dict(lo_um=3.7, hi_um=4.8, label="中波 3.7–4.8 μm", basis="SYS"),
    "LWIR": dict(lo_um=8.0, hi_um=12.0, label="长波 8.0–12.0 μm", basis="SYS"),
}

# 光谱采样：以波数步长定义。HITRAN 线宽在 1 atm 约 0.05–0.1 cm⁻¹，因此直接取
# 0.05 cm⁻¹（与吸收截面数据原生网格一致，避免重采样漏线）；更细只增成本。
# 收敛性校核见 06_校验/光谱大气校验.md。
SPECTRAL_STEP_CM = 0.05

# --------------------------------------------------------------------------- #
# 传感器：软件实际显示参数为锚点，辐射参数为设定/推导（口径见参数依据说明）
# --------------------------------------------------------------------------- #
SENSOR_BASE: Dict[str, object] = dict(
    band="MWIR",
    # —— 软件实测（DefaultPlanFile：默认想定 2 的红外传感器）——
    fov_h_deg=3.75,          # SYS
    fov_v_deg=3.0,           # SYS
    npx_h=1024,              # SYS
    npx_v=768,               # SYS
    frame_hz=50.0,           # SYS
    platform_h_m=8000.0,     # SYS
    depression_deg=-90.0,    # SYS（俯仰 -90°：正下视）
    # —— 设定/推导：与 IFOV 自洽的焦平面与光学链 ——
    pitch_m=28.7e-6,         # SET：1024×768 型制冷 MWIR 焦平面常用 25–30 μm 像元
    f_m=0.449,               # DER：f = pitch / IFOV = 28.7e-6 / 63.91e-6
    D_m=0.1497,              # DER：D = f / F#，取 F# = 3.0（SET）
    f_number=3.0,            # SET：制冷型 MWIR 常用 F/2–F/4，F/3 兼顾冷屏效率与口径
    netd_k=25e-3,            # SET：制冷型 InSb/SLS 在 F/3、300 K 下典型 20–30 mK
    tau_opt=0.80,            # SET：MWIR 光学链（含冷屏）典型 0.75–0.85
    jitter_mrad=0.020,       # SET：机载稳像后视线抖动典型 10–30 μrad
    f_elec_cyc_mrad=120.0,   # SET：电子学带宽折合 MTF 截止，远高于 Nyquist，影响可忽略
    k_mrtd=2.5,              # SET：MRTD(0)=k·NETD 的工程标定系数（Ratches/Lloyd 框架）
    cap_nyquist=True,        # SET：采样系统 f_max 上限取 Nyquist（1/(2·IFOV)）
)

# 参考系统两档（"工作模式"是单变量之一）
# --------------------------------------------------------------------------- #
# RECOG  —— 识别通道（参考系统，设定值）
#   IFOV = 15 μm / 1.20 m = 12.5 μrad → FOV = 1024×12.5 μrad = 0.733°×0.550°
#   Nyquist = 40 cyc/mrad，衍射截止 = D/λ = 0.30/4.25μm ≈ 70.6 cyc/mrad
#   → 探测器采样受限（f_nyq < f_cut），属长焦窄视场识别模式的典型量级。
#   设定依据：长焦窄视场是识别任务的常规工作模式；300 mm 口径 / F4 / 15 μm 像元 /
#   1024×768 / 25 mK 的组合与现役机载红外识别通道同一量级。全部为设定值，
#   已在 05_参数依据 登记，并通过口径/NETD/像元数单变量扫描给出敏感性。
# SEARCH —— 搜索通道（软件实测默认显示配置）
#   IFOV = 3.75°/1024 = 63.9 μrad，受采样严重限制，仅适合探测/大目标识别。
SENSOR_PRESETS: Dict[str, dict] = {
    # 视线抖动统一按"0.30 × IFOV"设定（稳像后残余抖动通常为亚像元量级，0.2–0.5 IFOV 是工程常见范围）
    "RECOG": dict(
        band="MWIR",
        fov_h_deg=0.7334, fov_v_deg=0.5500, npx_h=1024, npx_v=768,
        pitch_m=15e-6, f_m=1.20, D_m=0.30,
        netd_k=25e-3, tau_opt=0.80, jitter_mrad=0.00375,
        f_elec_cyc_mrad=120.0, k_mrtd=2.5, cap_nyquist=True, platform_h_m=8000.0,
    ),
    "SEARCH": dict(
        band="MWIR",
        fov_h_deg=3.75, fov_v_deg=3.0, npx_h=1024, npx_v=768,
        pitch_m=28.7e-6, f_m=0.449, D_m=0.1497,
        netd_k=25e-3, tau_opt=0.80, jitter_mrad=0.0192,
        f_elec_cyc_mrad=120.0, k_mrtd=2.5, cap_nyquist=True, platform_h_m=8000.0,
    ),
}

# --------------------------------------------------------------------------- #
# 判据：TTPF 概率模型 + 两套 N50 口径（必须绑定来源）
# --------------------------------------------------------------------------- #
CRITERIA: Dict[str, object] = dict(
    ttpf_exponent=2.0,       # LIT：Vollmerhausen & Jacobs 2004，TTPF 形状参数 E=2
)

N50_SETS: Dict[str, dict] = {
    # 主口径：NVESD/TTP metric（单位：目标上的周期数 cycles）
    "NVESD": dict(
        detect=4.0, recognize=16.5, identify=26.6,
        unit="cycles across target",
        source="Vollmerhausen R H, Jacobs E. The Targeting Task Performance (TTP) Metric."
               " NVESD, 2004. DOI:10.21236/ADA422493",
        basis="LIT",
    ),
    # 备口径：经典 Johnson（单位：线对数 line pairs，等价于目标上的周期数）
    "JOHNSON": dict(
        detect=2.0, recognize=8.0, identify=16.0,
        unit="line pairs across target",
        source="Johnson J. Analysis of Image Forming Systems. Proc. Image Intensifier Symposium,"
               " 1958: 249-273; Lloyd J M. Thermal Imaging Systems, 1975",
        basis="LIT",
    ),
}

# --------------------------------------------------------------------------- #
# 目标：软件模型库 6 个实际模型（OSG 顶点包围盒，1 单位 = 1 m）
# --------------------------------------------------------------------------- #
TARGETS: List[dict] = [
    dict(key="F16", name="F16 战斗机", kind="空中", dims=(9.660, 14.848, 4.574),
         z_m=500.0, eps=0.90, basis="SYS"),
    dict(key="F22", name="F22 战斗机", kind="空中", dims=(13.498, 18.601, 3.996),
         z_m=500.0, eps=0.90, basis="SYS"),
    dict(key="NIMITZ", name="尼米兹级航空母舰", kind="海面", dims=(85.730, 340.656, 75.223),
         z_m=0.0, eps=0.90, basis="SYS"),
    dict(key="ALBK", name="阿利伯克级驱逐舰", kind="海面", dims=(20.273, 151.324, 47.744),
         z_m=0.0, eps=0.90, basis="SYS"),
    dict(key="HM", name="悍马车", kind="地面", dims=(2.814, 5.091, 3.203),
         z_m=10.0, eps=0.90, basis="SYS"),
    dict(key="AGZFSC", name="爱国者导弹发射车", kind="地面", dims=(10.237, 22.567, 11.072),
         z_m=10.0, eps=0.90, basis="SYS"),
]

# 目标热状态（软件 Config.ini：温度范围 0–60 ℃；默认想定 3 档）
TARGET_STATES_C = [(20.0, "20 ℃（热交叉）"), (40.0, "40 ℃（中热）"), (60.0, "60 ℃（高热）")]

# --------------------------------------------------------------------------- #
# 背景（软件唯一实际背景模型：与那国岛）
# --------------------------------------------------------------------------- #
BACKGROUND: Dict[str, object] = dict(
    key="YNGD", name="与那国岛", temp_c=20.0, eps=0.95, basis="SYS",
    note="Config.ini：环境温度 20 ℃、温度范围 0–60 ℃、发射率按地物典型值设定",
)

# --------------------------------------------------------------------------- #
# 大气：以软件默认气象为基线，其余物理量按标准大气/文献
# --------------------------------------------------------------------------- #
ATMOS_BASE: Dict[str, object] = dict(
    aod550=0.587,        # DER：软件默认能见度 10 km → β550=3.912/10=0.391 km⁻¹ × 标高 1.5 km
    alpha=1.30,          # LIT：干净大陆气溶胶 Ångström 指数典型 1.2–1.5（Eck 1999 / OPAC）
    pwv_cm=1.28,         # DER：15 ℃/50%RH、水汽标高 2 km（ISO 2533 湿空气口径）
    h_aer_km=1.5,        # LIT：大陆气溶胶标高 1–2 km，取 1.5 km（LOWTRAN/OPAC 口径）
    h_wv_km=2.0,         # LIT：水汽标高典型 2 km（ISO 2533 湿空气廓线简化）
    t0_c=15.0,           # SYS：软件默认气象
    p0_hpa=1013.0,       # SYS：软件默认气象
    rh_pct=50.0,         # SYS：软件默认气象
    vis_km=10.0,         # SYS：软件默认气象（能见度 10000 m）
    lapse_k_per_km=6.5,  # LIT：ISO 2533 标准大气对流层温度直减率
    p_scale_km=8.0,      # LIT：ISO 2533 气压标高近似
    co2_ppm=420.0,       # LIT：2024 年全球平均 CO2 约 420 ppm（WMO GHG Bulletin）
    o3_ppb=35.0,         # LIT：近地面 O3 背景 20–50 ppb，取 35 ppb
    n2o_ppb=332.0,       # LIT：HITRAN2020 默认 N2O 332 ppb
    ch4_ppb=1930.0,      # LIT：HITRAN2020 默认 CH4 1930 ppb
    co_ppb=100.0,        # LIT：北半球背景 CO 约 80–120 ppb
    cn2=1e-15,           # LIT：弱湍流，ITU-R P.1817-1 白天近地面典型 1e-16–1e-14
)

# 大气廓线分层数：40 层（相对 20/80 层波段透过率误差 <0.1%，见 06_校验/光谱大气校验.md）
N_LAYERS = 40

# --------------------------------------------------------------------------- #
# 环境工况（真实气候统计，NASA POWER / MERRA-2，2015–2024，AERONET 站点）
# 每类给 AOD550 与 PWV 的 p10／中位／p90，以及该类气溶胶的 Ångström 指数
# --------------------------------------------------------------------------- #
ENVIRONMENTS: List[dict] = [
    # key, 名称, AOD550(p10,med,p90), PWV(cm)(p10,med,p90), alpha, 备注, 数据站点
    dict(key="DESERT", name="沙漠戈壁/干旱区", aod=(0.06, 0.19, 0.51), pwv=(0.24, 0.69, 2.15),
         alpha=0.35, sites="Dunhuang/Minqin/Dalanzadgad",
         note="Ångström α 取沙尘主导 0.2–0.5 中值"),
    dict(key="DUST", name="沙漠沙尘暴区", aod=(0.05, 0.30, 0.68), pwv=(0.46, 1.27, 2.21),
         alpha=0.25, sites="Kashi/Solar_Village",
         note="强沙尘事件 α 可低至 0.1–0.3"),
    dict(key="SEMIARID", name="半干旱草原（高原）", aod=(0.13, 0.33, 0.74), pwv=(0.38, 1.12, 2.77),
         alpha=1.10, sites="SACOL",
         note="混合型气溶胶 α 0.9–1.3"),
    dict(key="AGRI", name="农田/生物质燃烧", aod=(0.13, 0.44, 1.22), pwv=(0.60, 2.88, 5.47),
         alpha=1.60, sites="XiangHe/Taihu/Alta_Floresta",
         note="生物质燃烧 α 1.4–2.0"),
    dict(key="URBAN", name="城市/工业", aod=(0.14, 0.51, 1.27), pwv=(0.47, 1.99, 5.36),
         alpha=1.35, sites="Beijing/SONET_Shanghai",
         note="城市气溶胶 α 1.1–1.6"),
    dict(key="COASTAL", name="城市/海洋污染", aod=(0.19, 0.48, 1.06), pwv=(2.26, 4.33, 6.07),
         alpha=0.95, sites="Hong_Kong_PolyU",
         note="海陆混合 α 0.7–1.2"),
    dict(key="MARINE", name="海洋/清洁大气", aod=(0.06, 0.11, 0.45), pwv=(2.60, 4.06, 5.86),
         alpha=0.60, sites="Dongsha_Island/Lanai/Nauru",
         note="海洋气溶胶 α 0.4–0.8"),
    dict(key="ALPINE", name="高原清洁/高水汽", aod=(0.04, 0.14, 0.34), pwv=(0.16, 0.47, 1.65),
         alpha=1.20, sites="Lhasa",
         note="高原清洁大气 α 1.0–1.4"),
]

# --------------------------------------------------------------------------- #
# 基线工况（单变量实验的"其余条件全部固定"的那一组）
# --------------------------------------------------------------------------- #
BASELINE: Dict[str, object] = dict(
    scenario="BASE",
    band="MWIR",
    target_key="F16",
    target_temp_c=40.0,
    bg_temp_c=20.0,
    aod550=0.587,
    alpha=1.30,
    pwv_cm=1.28,
    cn2=1e-15,
    size_rule="sqrt_area",     # sqrt_area（主）| max_dim（备）
    n50_set="NVESD",           # NVESD（主）| JOHNSON（备）
    dT_intrinsic_K=20.0,       # = 40 ℃ - 20 ℃
)


# --------------------------------------------------------------------------- #
# 参数登记表导出
# --------------------------------------------------------------------------- #
def registry_rows() -> List[dict]:
    """把本文件中的全部参数展开成登记表行（供 05_参数依据 与报告表格使用）。"""
    rows: List[dict] = []

    def add(pid, name, sym, value, unit, cat, basis, source, conf, effect):
        rows.append(dict(param_id=pid, 参数=name, 符号=sym, 取值=value, 单位=unit,
                         类别=cat, 依据说明=basis, 来源=source, 置信度=conf,
                         影响方向=effect))

    add("BAND_MWIR", "中波波段", "λ_MWIR", "3.7–4.8", "μm", "软件实测",
        "模型 Config.ini 中波字段", "XGGDCOSSim2 Data/ModelData/*/Config.ini", "高",
        "决定衍射极限与大气吸收谱")
    add("BAND_LWIR", "长波波段", "λ_LWIR", "8.0–12.0", "μm", "软件实测",
        "模型 Config.ini 长波字段", "XGGDCOSSim2 Data/ModelData/*/Config.ini", "高",
        "长波衍射极限更松、水汽连续吸收更强")
    add("FOV", "视场", "FOV", "3.75×3.0", "deg", "软件实测",
        "默认想定红外传感器显示参数", "DefaultPlanFile 默认想定 2", "高", "决定 IFOV 与搜索范围")
    add("NPX", "探测器阵列", "N", "1024×768", "px", "软件实测",
        "默认想定红外传感器", "DefaultPlanFile", "高", "与 FOV 共同决定 IFOV")
    add("IFOV", "瞬时视场", "IFOV", "63.91", "μrad", "推导",
        "IFOV = FOV_h / N_h = 3.75°/1024", "由 FOV 与 NPX 推出", "高",
        "决定 Nyquist 频率与识别距离上限")
    add("PITCH", "像元间距", "p", "28.7", "μm", "设定",
        "1024×768 型制冷 MWIR 焦平面常用 25–30 μm；与 IFOV 自洽：f=p/IFOV", 
        "工程设定，待实测替换", "中", "与焦距同向缩放，不改变 IFOV/FOV 时对识别距离无影响")
    add("FOCAL", "焦距", "f", "0.449", "m", "推导", "f = p / IFOV", "由 PITCH 与 IFOV 推出", "高",
        "与口径共同决定 F#")
    add("APERTURE", "有效口径", "D", "0.1497", "m", "推导", "D = f / F#，F#=3.0",
        "由焦距与 F# 推出", "高", "决定衍射截止频率，是识别距离的硬上限")
    add("FNO", "F 数", "F#", "3.0", "-", "设定", "制冷型 MWIR 常用 F/2–F/4",
        "工程设定", "中", "F# 增大→口径减小→衍射极限变差")
    add("NETD", "噪声等效温差", "NETD", "25", "mK", "设定",
        "制冷型 InSb/SLS 在 F/3、300 K 下典型 20–30 mK", "器件手册典型值", "中",
        "决定 MRTD(0)=k·NETD，即对比度地板")
    add("TAU_OPT", "光学透过率", "τ_opt", "0.80", "-", "设定", "MWIR 光学链典型 0.75–0.85",
        "工程设定", "中", "按对比度线性折减（等价系统 NETD≈31 mK）")
    add("JITTER", "视线抖动", "σ_jit", "20", "μrad", "设定", "机载稳像后典型 10–30 μrad",
        "工程设定", "中", "高频 MTF 下降，使 f_max 提前收敛")
    add("KMRTD", "MRTD 标定系数", "k", "2.5", "-", "设定",
        "MRTD(0)=k·NETD 的工程近似（Ratches/Lloyd 框架）", "需实测标定", "低",
        "直接线性抬高对比度地板")
    add("N50_NVESD", "N50（NVESD/TTP）", "N50", "4.0 / 16.5 / 26.6", "cycles", "文献",
        "TTP metric 标定值（探测/识别/辨认）", "Vollmerhausen & Jacobs 2004, DOI:10.21236/ADA422493",
        "中", "N50 越大识别距离越近；与 Johnson 口径相差约 2 倍")
    add("N50_JOHNSON", "N50（经典 Johnson）", "N50", "2.0 / 8.0 / 16.0", "line pairs", "文献",
        "Johnson 判据原始口径", "Johnson 1958; Lloyd 1975", "中",
        "作为口径敏感性对照")
    add("TTPF_E", "TTPF 形状参数", "E", "2.0", "-", "文献", "TTPF 标准形式",
        "Vollmerhausen & Jacobs 2004", "中", "只改变 P(R) 过渡带陡缓，不改变 R50 位置")
    add("SPEC-GRID", "光谱网格步长", "Δν", "0.05", "cm⁻¹", "推导",
        "HITRAN 1 atm 线宽 0.05–0.1 cm⁻¹，取 0.05 cm⁻¹ 原生网格避免重采样漏线；收敛性已校核",
        "HITRAN2020 + 06_校验/光谱大气校验.md", "高", "过粗会低估气体吸收、高估波段透过率")
    add("TREF", "波段对比度加权参考温度", "T_ref", "293.15（背景温度）", "K", "推导",
        "对比度加权 w∝dB/dT 应取场景背景温度；原固定 288.15 K 为近似",
        "Planck 定律 + 本项目背景 20 ℃", "高", "仅微调波段加权，<1% 量级")
    add("ATM-ISO", "大气温度/气压廓线", "T(z), p(z)", "ISO 2533 分层", "-", "文献",
        "0–11 km 直减 6.5 K/km、11–20 km 等温 216.65 K；气压用气压公式而非单一指数标高",
        "ISO 2533:1975", "高", "8 km 处气压较原指数廓线低约 4.5%，影响干气体柱含量")
    add("ATM-CURV", "斜程几何", "R_E", "6371", "km", "文献",
        "球面地球弦长几何，层高取视线各点到地心距离减地球半径；不含大气折射",
        "WGS-84 平均半径；几何光学", "高", "百 km 级地面距离下透过率与等效斜距修正约 1–3%")
    add("ATM-RAYLEIGH", "Rayleigh 散射口径", "β_mol", "0.008735·λ^-4.08 / 8 km", "km⁻¹", "文献",
        "0.008735·λ^-4.08 为 550 nm 垂直光学厚度系数（550 nm 处 τ≈0.10），除以 8 km 标高得地面消光系数",
        "6S / Bodhaine 1999；原式误作每 km 系数、偏小 1.43 倍", "高",
        "红外波段消光 <1e-5 km⁻¹，对 R50 无可见影响，属口径修正")
    add("ATM-SPECIES", "光谱吸收物种", "H2O/CO2/O3/N2O/CO/CH4", "6 种", "-", "文献",
        "HITRAN2020 逐线 Voigt，三温度 250/280/300 K，压力 1 atm，cm²/molecule",
        "HITRAN2020（Gordon 2022）；HAPI 1.3；参考项目 hitran_slant 线表", "高",
        "决定 MWIR 4.3 μm 与 LWIR 9.6 μm 吸收带强度")
    for t in TARGETS:
        add(f"TGT_{t['key']}", f"目标包围盒-{t['name']}", "W×L×H",
            "×".join(f"{v:.3f}" for v in t["dims"]), "m", "软件实测",
            "OSG 顶点包围盒，按 1 单位 = 1 m", f"XGGDCOSSim2 ModelData/Target/{t['key']}",
            "中（未几何标定）", "特征尺寸直接决定分辨率受限的识别距离")
    add("SIZE_RULE", "特征尺寸口径", "D_eff", "sqrt(W×H)（主）/ max(W,L,H)（备）", "m", "推导",
        "等效方目标口径：与 TTP 的 √A_t 思路一致；备选为最大边口径",
        "NVESD TTP metric 思路", "中", "两口径 R50 相差约 1.5–2.3 倍")
    add("EPS_T", "目标发射率", "ε_t", "0.90", "-", "文献", "金属/涂装目标 3–5 μm 典型 0.85–0.95",
        "Salisbury & D'Aria 1994; ASTER 库", "中", "ε 通过 ε_t·ΔB(T_t−T_b) 线性缩放对比度")
    add("EPS_B", "背景发射率", "ε_b", "0.95", "-", "文献", "植被/土壤 8–14 μm 典型 0.94–0.97",
        "Salisbury & D'Aria 1992", "中",
        "与目标反射项共同构成辐亮度；在“环境辐亮度=背景黑体”假设下对比度化简为 ε_t·ΔB")
    add("T_BG", "背景温度", "T_bg", "20", "℃", "软件实测", "与那国岛 Config.ini 环境温度",
        "ModelData/Background/yngd/Config.ini", "高", "与目标温度共同决定固有温差")
    add("T_STATE", "目标热状态", "T_t", "20/40/60", "℃", "软件实测",
        "Config.ini 温度范围 0–60 ℃ 的三档取值", "目标模型 Config.ini", "高",
        "热交叉（20 ℃）时对比度极小，是临界状态的关键工况")
    add("AOD550", "550 nm 气溶胶光学厚度", "τ_a(550)", "0.587（基线）", "-", "推导",
        "软件默认能见度 10 km → β550=3.912/10 → × 标高 1.5 km", "Koschmieder 1924 + WMO-No.8 2021",
        "高", "决定气溶胶消光，是霾/沙尘工况的主控参数")
    add("ALPHA", "Ångström 指数", "α", "1.30（干净大陆）", "-", "文献",
        "大陆型 1.2–1.5、城市 1.1–1.6、海洋 0.4–0.8、沙尘 0.2–0.5",
        "Ångström 1929; Eck et al. 1999", "高", "同等 AOD 下 α 越小，长波衰减越强")
    add("PWV", "可降水量", "PWV", "1.28（基线）", "cm", "推导",
        "15 ℃/50%RH + 2 km 水汽标高", "ISO 2533 湿空气廓线", "高", "决定水汽吸收带强度")
    add("H_AER", "气溶胶标高", "H_a", "1.5", "km", "文献", "大陆型 1–2 km",
        "LOWTRAN 7 / OPAC", "中", "AOD↔地面消光的换算系数，线性影响透过率")
    add("CN2", "折射率结构常数", "Cn²", "1e-15（基线）", "m^-2/3", "文献",
        "工程约定分级：弱 1e-16、中 1e-15、强 1e-14、极强 1e-13（Andrews & Phillips / Kopeika 教材体系）；"
        "ITU-R P.1817-1 只给定性湍流描述、未给 Cn² 数值表，不可写成“ITU 标准值”",
        "Andrews & Phillips 2005; Kopeika 1998; ITU-R P.1817-1（定性）", "中", "决定湍流 MTF，仅在 Cn²≥1e-14 时显著")
    add("CO2", "CO2 混合比", "x_CO2", "420", "ppm", "文献", "2024 年全球平均",
        "WMO GHG Bulletin", "高", "4.3 μm 带吸收的主控量")
    add("O3", "O3 混合比", "x_O3", "35", "ppb", "文献", "近地面背景 20–50 ppb",
        "HITRAN2020 默认大气", "中", "9.6 μm 带吸收，下视短路径影响小")
    add("MINOR", "N2O/CH4/CO 背景浓度", "x", "332/1930/100", "ppb", "文献",
        "HITRAN2020 默认大气", "HITRAN2020", "高", "次要吸收体，量级 <1%")
    return rows


if __name__ == "__main__":
    import csv, os, sys
    out = sys.argv[1] if len(sys.argv) > 1 else "参数依据登记表_自动导出.csv"
    rows = registry_rows()
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out, len(rows), "rows")
