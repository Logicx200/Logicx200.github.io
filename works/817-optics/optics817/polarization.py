# -*- coding: utf-8 -*-
"""第四章 / 第五章 光在各向异性介质中的传播、晶体的感应双折射。

覆盖考点：
    * 单轴晶体的 o 光、e 光折射率与走离角，主截面、主平面
    * 偏振棱镜、波片（1/4 波片、1/2 波片）、补偿器
    * 晶体的偏光干涉（正交/平行偏振器下）
    * 旋光性
    * 线性电光效应（KDP 等）、声光效应（喇曼-纳斯/布喇格）、法拉第效应
"""
from __future__ import annotations

import numpy as np

from .wave import jones_waveplate  # 复用波片琼斯矩阵

# 常见晶体参数（lambda ≈ 589 nm，室温）
CRYSTALS = {
    "石英 quartz": dict(no=1.5443, ne=1.5534, positive=True),
    "方解石 calcite": dict(no=1.6584, ne=1.4864, positive=False),
    "铌酸锂 LiNbO3": dict(no=2.2865, ne=2.2028, positive=False),
    "KDP": dict(no=1.5115, ne=1.4699, positive=False),
    "云母 mica": dict(no=1.582, ne=1.588, positive=True),
}


def is_positive(no: float, ne: float) -> bool:
    """正晶体：ne > no（石英）；负晶体：ne < no（方解石）。"""
    return bool(ne > no)


def extraordinary_index(no: float, ne: float, theta):
    """e 光折射率 n_e(theta)，theta 为波法线与光轴夹角。

        1/n_e^2(theta) = cos^2(theta)/no^2 + sin^2(theta)/ne^2
        n_e(theta) = no*ne / sqrt(ne^2 cos^2(theta) + no^2 sin^2(theta))

    theta = 0（沿光轴）：n = no，此时无双折射；
    theta = 90°（垂直光轴）：n = ne，双折射最显著。
    """
    th = np.asarray(theta, dtype=float)
    return no * ne / np.sqrt(ne ** 2 * np.cos(th) ** 2 + no ** 2 * np.sin(th) ** 2)


def walk_off_angle(no: float, ne: float, theta):
    """e 光走离角（光线与波法线夹角）rho：

        tan(rho) = (1 - (no/ne)^2) tan(theta) / (1 + (no/ne)^2 tan^2(theta))
    方解石在 ~45° 附近 rho 约 6.2°。
    """
    th = np.asarray(theta, dtype=float)
    r = (no / ne) ** 2
    return np.arctan((1.0 - r) * np.tan(th) / (1.0 + r * np.tan(th) ** 2))


def retardance(no: float, ne: float, d: float, lam: float, theta: float = np.pi / 2):
    """波片相位延迟 delta = 2 pi |no - ne| d / lambda（theta=90° 时光垂直光轴）。"""
    return 2.0 * np.pi * abs(no - ne) * d / lam


def waveplate_thickness(lam: float, no: float, ne: float, kind: str = "quarter", m: int = 0) -> float:
    """波片几何厚度。

    kind = 'quarter'  -> (2m+1) lambda / (4 |no-ne|)
    kind = 'half'     -> (2m+1) lambda / (2 |no-ne|)
    kind = 'full'     -> lambda / |no-ne|
    """
    dn = abs(no - ne)
    if kind == "quarter":
        return (2 * m + 1) * lam / (4.0 * dn)
    if kind == "half":
        return (2 * m + 1) * lam / (2.0 * dn)
    if kind == "full":
        return lam / dn
    raise ValueError("kind 只能是 'quarter' / 'half' / 'full'")


def waveplate_output(jones_in, delta: float, theta: float):
    """波片对入射偏振态的作用：J_out = W(delta, theta) @ J_in。"""
    return jones_waveplate(delta, theta) @ np.asarray(jones_in, dtype=complex)


def polarization_interference_transmission(delta, phi: float, mode: str = "crossed"):
    """晶片偏光干涉透射率（晶片置于两偏振器之间）。

    phi   : 晶片光轴与起偏器透振方向的夹角
    mode  : 'crossed' 正交偏振器 -> T = sin^2(2phi) sin^2(delta/2)
            'parallel' 平行偏振器 -> T = 1 - sin^2(2phi) sin^2(delta/2)
    """
    s2 = np.sin(2.0 * phi) ** 2 * np.sin(np.asarray(delta) / 2.0) ** 2
    return s2 if mode == "crossed" else 1.0 - s2


def optical_rotation(verdet_or_rho: float, d: float, B: float | None = None):
    """旋光角或法拉第旋转角。

    * 自然旋光：theta = rho * d（rho 为旋光率，rad/m）
    * 法拉第效应：theta = V * B * d（V 为费尔德常数，B 为磁感应强度）
    给 B 时按法拉第效应计算，否则按自然旋光。
    """
    if B is None:
        return verdet_or_rho * d
    return verdet_or_rho * B * d


def pockels_half_wave_voltage(lam: float, no: float, r63: float, longitudinal: bool = True) -> float:
    """KDP 类晶体的半波电压。

    纵向（电场沿光传播方向，通光方向加电压）：V_pi = lambda / (2 no^3 r63)
    横向（电场垂直光传播方向）：V_pi = lambda d / (2 no^3 r63 L)
    这里返回纵向值（KDP 约 7.5 kV @ 550 nm）。
    """
    return lam / (2.0 * no ** 3 * r63)


def pockels_phase_retardance(lam: float, no: float, r63: float, V: float, L: float = 1.0, d: float = 1.0):
    """线性电光效应引入的相位延迟（横向运用）：

        delta = 2 pi no^3 r63 V L / (lambda d)
    """
    return 2.0 * np.pi * no ** 3 * r63 * V * L / (lam * d)


def acousto_optic_bragg_angle(lam: float, acoustic_velocity: float, acoustic_freq: float):
    """布喇格声光衍射角 sin(theta_B) = lambda / (2 * Lambda)，Lambda = v/f。"""
    lam_ac = acoustic_velocity / acoustic_freq
    s = lam / (2.0 * lam_ac)
    return float(np.arcsin(np.clip(s, -1, 1)))


def acousto_optic_raman_nath_number(lam: float, L: float, lambda_acoustic: float, n: float = 1.0) -> float:
    """喇曼-纳斯判据 Q = 2 pi lambda L / (n Lambda^2)。

    Q >> 1（一般 Q > 4 pi）为布喇格衍射；Q << 1 为喇曼-纳斯衍射（出现多级）。
    lam 为光波长，L 为声束宽度，lambda_acoustic 为声波波长。
    """
    return 2.0 * np.pi * lam * L / (n * lambda_acoustic ** 2)


def brewster_stack_reflectance(n_layers: int, n_plate: float, n_air: float = 1.0):
    """布儒斯特窗堆（偏振棱镜/激光腔窗）的反射率近似：R ≈ (2N * r_p? ) 见文档。

    实际计算请用 wave.reflectance_multilayer_normal，这里仅给出直观估计：
    每片以布儒斯特角放置时 p 分量反射为 0，s 分量反射率 R_s 由菲涅耳公式给出。
    """
    from .wave import fresnel, brewster_angle

    th = brewster_angle(n_air, n_plate)
    R_s = fresnel(n_air, n_plate, th)["Rs"]
    return 1.0 - (1.0 - R_s) ** (2 * n_layers)
