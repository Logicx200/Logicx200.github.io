# -*- coding: utf-8 -*-
"""第十章 光学仪器。

覆盖考点：
    * 眼睛：结构、调节能力（远点/近点/明视距离）、近视/远视/散光的校正
    * 放大镜、显微镜、望远镜的原理、放大率与分辨本领
"""
from __future__ import annotations

import numpy as np

D_MINGSHI = 0.25  # 明视距离 250 mm
EYE_RESOLUTION = 1.0 / 60.0 * np.pi / 180.0  # 人眼最小分辨角 ≈ 1'（弧度）


# ---------------------------------------------------------------- 眼睛
def eye_accommodation(far_point: float, near_point: float = D_MINGSHI):
    """眼睛的调节范围：远点、近点（单位 m，均为正值表示眼前距离）。

    调节能力（屈光度）A = 1/近点 - 1/远点。
    """
    return dict(far=far_point, near=near_point,
                range_diopters=1.0 / near_point - 1.0 / far_point)


def myopia_correction_distance(far_point: float) -> float:
    """近视眼校正：远点 F 处的物体要成像在远点，镜片焦距 f = -F。

    焦度 Phi = -1/F（屈光度 D，负值表示凹透镜）。
    """
    return -1.0 / far_point


def eyeglass_focal_length(object_distance: float, image_distance: float) -> float:
    """配镜：物在 object_distance（正，眼前），像成在 image_distance（正，眼前）。

    薄透镜 1/v + 1/u = 1/f 的反向使用：此处把物方距离 u 与像方距离 v 都取正。
    """
    return 1.0 / (1.0 / object_distance + 1.0 / image_distance)


# ---------------------------------------------------------------- 放大镜
def magnifier_angular_magnification(f: float, D: float = D_MINGSHI, relaxed: bool = True) -> float:
    """放大镜视角放大率。

    眼睛调焦到无穷远（放松）： Gamma = D / f
    眼睛调焦到明视距离：     Gamma = D / f + 1
    """
    return D / f + (0.0 if relaxed else 1.0)


# ---------------------------------------------------------------- 显微镜
def microscope_total_magnification(optical_tube_length: float, f_objective: float,
                                   f_eyepiece: float, D: float = D_MINGSHI) -> float:
    """显微镜总放大率 Gamma = beta_obj * Gamma_eye = -(Delta/f_o') * (D/f_e')。

    Delta 为光学筒长（物镜后焦点到目镜前焦点的距离），返回绝对值。
    """
    beta_obj = optical_tube_length / f_objective
    return abs(beta_obj * D / f_eyepiece)


def numerical_aperture(n: float, u: float) -> float:
    """数值孔径 NA = n sin(u)，u 为物方孔径角。"""
    return n * np.sin(u)


def microscope_resolution(lam: float, NA: float) -> float:
    """显微镜最小分辨距离 d = 0.61 lambda / NA（瑞利判据）。"""
    return 0.61 * lam / NA


def microscope_magnification_limit(NA: float, lam: float = 550e-9,
                                   eye_res: float = EYE_RESOLUTION) -> float:
    """有效放大率上限：再放大也不会增加信息，Gamma_max ≈ 眼睛分辨角/物镜分辨角。"""
    return eye_res / microscope_resolution(lam, NA)


# ---------------------------------------------------------------- 望远镜
def telescope_magnification(f_objective: float, f_eyepiece: float) -> float:
    """开普勒望远镜视角放大率 Gamma = f_o' / f_e'（绝对值；成倒像）。"""
    return abs(f_objective / f_eyepiece)


def telescope_length(f_objective: float, f_eyepiece: float) -> float:
    """物镜与目镜间距（焦面重合，无焦系统）L = f_o' + f_e'。"""
    return f_objective + f_eyepiece


def telescope_resolution(lam: float, D: float) -> float:
    """望远镜最小分辨角 theta = 1.22 lambda / D（弧度）。"""
    return 1.22 * lam / D


def telescope_resolution_arcsec(lam: float, D: float) -> float:
    """望远镜最小分辨角（角秒）。"""
    return np.degrees(telescope_resolution(lam, D)) * 3600.0


def exit_pupil_diameter(D_objective: float, mag: float) -> float:
    """望远镜出瞳直径 D' = D / Gamma（也是物镜口径与放大率的关系）。"""
    return D_objective / mag


def eye_relief_requirement(D_exit_pupil: float, eye_relief: float):
    """出瞳直径与出瞳距离的经验要求：出瞳直径宜 ≥ 2 mm，出瞳距离 ≥ 5~10 mm。"""
    return dict(exit_pupil=D_exit_pupil, eye_relief=eye_relief,
                ok=(D_exit_pupil >= 2e-3) and (eye_relief >= 5e-3))
