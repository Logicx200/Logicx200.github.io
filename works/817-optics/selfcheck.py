# -*- coding: utf-8 -*-
"""selfcheck.py —— 用仿真反过来验证公式。

这是本套材料最重要的用法：**每背下一个公式，就让程序把它算一遍**，
两者的差值就是你的错题来源。

运行：  python selfcheck.py
全部通过会打印 [OK] 行；任一项失败抛 AssertionError。
"""
from __future__ import annotations

import numpy as np

import optics817 as o8

PASS = 0


def check(name: str, got, want, tol: float = 1e-9):
    global PASS
    got = np.asarray(got, dtype=float)
    want = np.asarray(want, dtype=float)
    ok = np.allclose(got, want, atol=tol, rtol=0)
    flag = "OK  " if ok else "FAIL"
    print(f"[{flag}] {name:<52} 计算值={np.round(got, 6)}  期望={np.round(want, 6)}")
    assert ok, name
    PASS += 1


print("=" * 78)
print("第一章 光的电磁理论基础")
print("=" * 78)
# 正入射 air->glass(n=1.5)：R = ((n1-n2)/(n1+n2))^2 = 0.04
f = o8.wave.fresnel(1.0, 1.5, 0.0)
check("正入射反射率 R = 0.04", f["Rs"], 0.04)
check("正入射 R_s = R_p", f["Rp"], f["Rs"])
check("无吸收时 T = 1 - R", f["Ts"], 0.96)
# 布儒斯特角: tan(thetaB) = 1.5
thB = o8.wave.brewster_angle(1.0, 1.5)
check("布儒斯特角 = 56.31 deg", np.degrees(thB), np.degrees(np.arctan(1.5)))
check("布儒斯特角处 rp = 0", o8.wave.fresnel(1.0, 1.5, thB)["Rp"], 0.0, tol=1e-15)
# 全反射临界角: sin(thetaC) = 2/3
thC = o8.wave.critical_angle(1.5, 1.0)
check("临界角 = arcsin(2/3)", np.degrees(thC), np.degrees(np.arcsin(2 / 3)))
check("临界角外 R = 1", o8.wave.fresnel(1.5, 1.0, np.radians(50))["Rs"], 1.0)
# 全反射相移：用 fresnel 的复数结果交叉验证
th = np.radians(50.0)
fr = o8.wave.fresnel(1.5, 1.0, th)
ds, dp = o8.wave.tir_phase_shifts(1.5, 1.0, th)
check("全反射 rs 相位 = -ds", np.angle(fr["rs"]), -ds, tol=1e-12)
check("全反射 rp 相位 = -dp", np.angle(fr["rp"]), -dp, tol=1e-12)
check("全反射 dp - ds > 0", np.sign(dp - ds), 1.0)
# 单层 1/4 波长增透膜 n = sqrt(n0 ns) 时 R = 0
n_ar = np.sqrt(1.0 * 1.5)
check("1/4 波长膜 R = 0 (n=sqrt(n0*ns))", o8.wave.quarter_wave_reflectance(1.0, n_ar, 1.5), 0.0)
# 特征矩阵法与解析式一致
lam0 = 550e-9
R_tmm = o8.wave.reflectance_multilayer_normal([1.0, n_ar, 1.5], [lam0 / (4 * n_ar)], lam0)
check("TMM 单层增透膜 R ≈ 0 @ lambda0", R_tmm, 0.0, tol=1e-12)
# 琼斯：线偏振片 x 后接 +45° 检偏 -> 一半强度
J = o8.wave.jones_linear_polarizer(0.0) @ o8.wave.jones_linear(0.0)
I = np.abs(o8.wave.jones_linear_polarizer(np.pi / 4) @ J) ** 2
check("马吕斯：0deg 偏振过 45deg 检偏 I = 0.5", I.sum(), 0.5)
# 1/4 波片把 45° 线偏振变成圆偏振，S3/S0 = ±1
J45 = o8.wave.jones_linear(np.pi / 4)
Jq = o8.wave.jones_waveplate(np.pi / 2, 0.0) @ J45
check("1/4 波片：线偏振 -> 圆偏振 |S3|/S0 = 1",
      abs(o8.wave.stokes_from_jones(Jq)[3] / o8.wave.stokes_from_jones(Jq)[0]), 1.0, tol=1e-12)

print()
print("=" * 78)
print("第二章 光的干涉")
print("=" * 78)
check("杨氏双缝条纹间距 = lambda z / d",
      o8.interference.fringe_spacing(600e-9, 0.5e-3, 1.0), 600e-9 / 0.5e-3)
# 双缝：d 不变时条纹间距与 lambda 成正比（一级极大位置）
x1 = 600e-9 * 1.0 / 0.5e-3
check("双缝一级极大处 I = Imax",
      o8.interference.double_slit_intensity(x1, 600e-9, 0.5e-3, z=1.0), 1.0)
check("双缝暗纹处 I = 0",
      o8.interference.double_slit_intensity(x1 / 2, 600e-9, 0.5e-3, z=1.0), 0.0, tol=1e-15)
# 爱里公式：r = 0.5 时 Tmax = 1, Tmin = 1/(1+F)
r = 0.5
F = 4 * r ** 2 / (1 - r ** 2) ** 2
check("爱里公式 Tmax = 1", o8.interference.airy_transmission(0.0, r), 1.0)
check("爱里公式 Tmin = 1/(1+F)", o8.interference.airy_transmission(np.pi, r), 1.0 / (1 + F))
check("精细度 F* = pi sqrt(R)/(1-R)", o8.interference.finesse(r),
      np.pi * np.sqrt(r ** 2) / (1 - r ** 2))
# 牛顿环：中心暗、第 m 暗环 r = sqrt(m lambda R)
check("牛顿环中心为暗斑", o8.interference.newton_rings_intensity(0.0, 600e-9, 1.0), 0.0)
check("牛顿环第 3 暗环 r = sqrt(3 lambda R)",
      o8.interference.newton_dark_radius(3, 600e-9, 1.0), np.sqrt(3 * 600e-9))
# 迈克尔逊：d 改变 lambda/4 使中心由亮变暗
I0 = o8.interference.michelson_circular_intensity(0.0, 0.0, 600e-9)
I1 = o8.interference.michelson_circular_intensity(0.0, 600e-9 / 4, 600e-9)
check("迈克尔逊 d 变化 lambda/4 由亮变暗", I0 - I1, 1.0)

print()
print("=" * 78)
print("第三章 光的衍射")
print("=" * 78)
# 单缝：第一暗纹 a sin(theta) = lambda
a, lam, z = 0.1e-3, 600e-9, 1.0
x_dark = lam * z / a
check("单缝第一暗纹处 I = 0",
      o8.diffraction.single_slit_intensity(x_dark, lam, a, z), 0.0, tol=1e-12)
check("单缝中央亮纹半角宽 = lambda/a", x_dark / z, lam / a)
# 圆孔艾里斑
check("艾里斑半径 = 1.22 lambda z / D",
      o8.diffraction.airy_radius(600e-9, 1e-3, 1.0), 1.22 * 600e-9 * 1.0 / 1e-3)
check("瑞利判据 theta = 1.22 lambda / D",
      o8.diffraction.rayleigh_angle(600e-9, 1e-3), 1.22 * 600e-9 / 1e-3)
# 光栅方程与分辨本领（600 线/mm → d = 1.667 μm；缝宽为周期的 1/3）
d, N = 1e-3 / 600.0, 12000
a_grating = 1e-3 / 1800.0
m = 2
check("光栅方程 d sin(theta) = m lambda",
      d * np.sin(o8.diffraction.grating_angle(m, 550e-9, d)), m * 550e-9)
check("光栅分辨本领 R = mN", o8.diffraction.grating_resolving_power(m, N), m * N)
check("光栅最高级次 floor(d/lambda)",
      o8.diffraction.grating_max_order(550e-9, d), 3)
check("光栅缺级：d/a = 3 时第 3,6,9 级缺",
      o8.diffraction.grating_intensity(3 * 550e-9 / d * 1.0, 550e-9, d, 12000,
                                       a=a_grating, z=1.0), 0.0, tol=1e-10)
# 菲涅耳圆孔轴向强度：N=1 时 I = 4 I0（波带片增亮的根据）
check("菲涅耳圆孔 N=1 时 I = 4 I0",
      o8.diffraction.circular_aperture_axial_intensity(1.0 ** 2 / 600e-9, 1.0, 600e-9), 4.0)
check("菲涅耳圆孔 N=2 时 I = 0",
      o8.diffraction.circular_aperture_axial_intensity(2.0 ** 2 / (2 * 600e-9), 2.0, 600e-9), 0.0,
      tol=1e-12)
# 菲涅耳直边：几何阴影边界处 I = I0/4
check("直边衍射边界 I = I0/4",
      o8.diffraction.fresnel_edge_intensity(0.0, 600e-9, 1.0), 0.25, tol=1e-12)
check("直边衍射照明区远处 I -> I0（带菲涅耳振荡）",
      o8.diffraction.fresnel_edge_intensity(0.1, 600e-9, 1.0), 1.0, tol=1e-2)
check("直边衍射阴影区深处 I -> 0",
      o8.diffraction.fresnel_edge_intensity(-0.05, 600e-9, 1.0), 0.0, tol=3e-2)
# 波带片焦距 f_m = a^2/(m lambda)
mm, ff = o8.diffraction.zone_plate_focal_lengths(1e-3, 600e-9, 3)
check("波带片主焦距 f1 = a^2/lambda", ff[0], 1e-3 ** 2 / 600e-9)

print()
print("=" * 78)
print("第三章第 5 节 / 傅里叶光学")
print("=" * 78)
N2, dx = 512, 5e-6
U0, X, Y, x = o8.fourier_optics.circ_aperture(N2, dx, 20 * dx)
U1, dxo = o8.fourier_optics.angular_spectrum(U0, 600e-9, 1e-3, dx)
check("角谱法传播保持能量", np.sum(np.abs(U1) ** 2), np.sum(np.abs(U0) ** 2), tol=1e-8)
check("角谱法传播 dx 不变", dxo, dx)
Uf, dxf, xf = o8.fourier_optics.fresnel_fft(U0, 600e-9, 0.5, dx)
check("菲涅耳单次 FFT 输出间距 = lambda z/(N dx)", dxf, 600e-9 * 0.5 / (N2 * dx), tol=1e-15)
check("菲涅耳单次 FFT 保持能量（近似）", np.sum(np.abs(Uf) ** 2) * dxf ** 2,
      np.sum(np.abs(U0) ** 2) * dx ** 2, tol=1e-6)
check("圆孔 OTF 在 f=0 处 = 1", o8.fourier_optics.otf_circular(0.0, 1e5), 1.0)
check("圆孔 OTF 在截止频率处 = 0", o8.fourier_optics.otf_circular(1e5, 1e5), 0.0)

print()
print("=" * 78)
print("第四 / 五章 各向异性介质与感应双折射")
print("=" * 78)
no, ne = 1.6584, 1.4864  # 方解石
check("e 光沿光轴 theta=0 时 n = no（无双折射）",
      o8.polarization.extraordinary_index(no, ne, 0.0), no)
check("e 光垂直光轴 theta=90deg 时 n = ne",
      o8.polarization.extraordinary_index(no, ne, np.pi / 2), ne)
check("方解石为负晶体", o8.polarization.is_positive(no, ne), 0.0)
# 方解石最大走离角约 6.2 度
rho = np.degrees(np.abs(o8.polarization.walk_off_angle(no, ne, np.linspace(0, np.pi / 2, 20001))))
check("方解石最大走离角 ≈ 6.2 deg", rho.max(), 6.2, tol=0.15)
# 1/4 波片厚度
check("石英 1/4 波片厚度 = lambda/(4|no-ne|)",
      o8.polarization.waveplate_thickness(589e-9, 1.5443, 1.5534, "quarter"),
      589e-9 / (4 * abs(1.5443 - 1.5534)))
# 正交偏振器 + 晶片：phi = 45° 且 delta = pi 时全透
check("偏光干涉 crossed: T(phi=45,delta=pi) = 1",
      o8.polarization.polarization_interference_transmission(np.pi, np.pi / 4), 1.0)
check("偏光干涉 crossed: phi=0 时 T = 0",
      o8.polarization.polarization_interference_transmission(np.pi, 0.0), 0.0)
# KDP 纵向半波电压 ~7.5 kV @550nm
check("KDP 纵向半波电压 ≈ 7.5 kV",
      o8.polarization.pockels_half_wave_voltage(550e-9, 1.512, 10.6e-12) / 1e3, 7.5, tol=0.2)
# 布喇格声光
v, fac = 4000.0, 80e6
check("声光布喇格角 sin(thetaB) = lambda/(2 Lambda)",
      np.sin(o8.polarization.acousto_optic_bragg_angle(633e-9, v, fac)), 633e-9 / (2 * v / fac))

print()
print("=" * 78)
print("第七 / 八 / 九章 应用光学")
print("=" * 78)
# 单个折射球面：实物成实像（r=100mm, l=-300mm, 1 -> 1.5）
l, rr, n1, n2 = -300.0, 100.0, 1.0, 1.5
lp, beta = o8.geometrical.refraction_sphere(l, rr, n1, n2)
check("单折射球面 l' 满足 n'/l' - n/l = (n'-n)/r",
      n2 / lp - n1 / l, (n2 - n1) / rr)
check("单折射球面 l' = 900 mm", lp, 900.0)
check("单折射球面 beta = -2", beta, -2.0)
# 用近轴矩阵独立核对同一个成像
_s = o8.geometrical.ParaxialSystem(
    [{"type": "gap", "d": 300.0}, {"type": "refract", "R": 100.0, "n_after": 1.5}])
_t, _M, _b = _s.image_plane()
check("矩阵法单折射面像距与公式一致", _t, lp, tol=1e-9)
check("矩阵法放大率与公式一致", _b, beta, tol=1e-12)
# 单折射面 f' = n' r/(n'-n)
check("单折射球面 f' = n' r /(n'-n)", o8.geometrical.paraxial_focus_sphere(rr, n1, n2),
      1.5 * 100.0 / 0.5)
# 薄透镜：物在 2f 处，像在 2f 处，beta = -1
check("高斯公式 1/v+1/u=1/f", o8.geometrical.gauss_image(200.0, 100.0), 200.0)
check("物在 2f 处 beta = -1",
      o8.geometrical.transverse_magnification(-200.0, 200.0, 1.0, 1.0), -1.0)
# 近轴矩阵：单个薄透镜
sysl = o8.geometrical.ParaxialSystem([{"type": "lens", "f": 0.1}])
check("薄透镜 f' = -1/C = 0.1", sysl.effective_focal_length(), 0.1)
check("薄透镜后焦距 = 0.1", sysl.back_focal_distance(), 0.1)
check("薄透镜前焦距 = 0.1（向左）", sysl.front_focal_distance(), 0.1)
# 双光组组合公式 vs 矩阵
for f1, f2, dd in [(0.1, 0.1, 0.05), (0.1, 0.05, 0.12), (0.2, -0.1, 0.05)]:
    a = o8.geometrical.two_lens_combination(f1, f2, dd)
    b = o8.geometrical.two_lens_combination_from_matrix(f1, f2, dd)
    check(f"双光组 f1={f1} f2={f2} d={dd}: 公式 f' = 矩阵 f'", a["f"], b["f"], tol=1e-12)
    check(f"双光组 f1={f1} f2={f2} d={dd}: 公式 lF' = 矩阵 lF'", a["lFp"], b["lFp"], tol=1e-12)
    check(f"双光组 f1={f1} f2={f2} d={dd}: 公式 lF = 矩阵 lF", a["lF"], b["lF"], tol=1e-12)
# 球差：正透镜边缘光线聚焦更近（球差为负）
dL = o8.geometrical.longitudinal_spherical_aberration([5e-3, 10e-3, 20e-3], 50e-3, 1.0, 1.5)
check("正折射面球差 < 0（边缘光线交点更近）", np.all(dL < 0), True)
check("球差随入射高度单调增大",
      np.all(np.diff(np.abs(dL)) > 0), True)
# 近轴光路计算与矩阵法一致
surf = [dict(r=50e-3, d=5e-3, n=1.5), dict(r=-50e-3, d=0.05, n=1.0)]
tr = o8.geometrical.paraxial_trace(surf, y1=1e-3, u1=0.0, n_start=1.0)
Ms = o8.geometrical.ParaxialSystem(
    [{"type": "refract", "R": 50e-3, "n_after": 1.5},
     {"type": "gap", "d": 5e-3},
     {"type": "refract", "R": -50e-3, "n_after": 1.0}])
M, nn = Ms.matrix()
check("y-u 递推与矩阵法 y 一致", tr[-1]["y"], M[0, 0] * 1e-3 + M[0, 1] * 0.0, tol=1e-15)
check("y-u 递推与矩阵法 u 一致", tr[-1]["u_after"], M[1, 0] * 1e-3, tol=1e-15)

print()
print("=" * 78)
print("光阑判定（第九章核心考点）")
print("=" * 78)
# 经典模型：物在 L1 前 40mm —— L1(f=100mm, D=40mm) —— 60mm —— 光阑 P(D=20mm)
systems = o8.geometrical.ParaxialSystem([
    {"type": "gap", "d": 0.04},                   # 物面到第一面
    {"type": "lens", "f": 0.1, "semi": 0.02},     # L1，口径 40mm
    {"type": "gap", "d": 0.06},
    {"type": "stop", "semi": 0.01},               # 光阑 P，口径 20mm
])
stop, data = systems.aperture_stop()
for dd_ in data:
    print(f"    元件 {dd_['index']} ({systems.elements[dd_['index']]['type']}): "
          f"半口径 {dd_['semi']*1e3:.1f} mm, 物方孔径角 u = {dd_['u_object']*1e3:.4f} mrad")
print(f"    -> 孔径光阑是元件 {stop}")
check("孔径光阑应为光阑 P（元件 3）", stop, 3)
ep = systems.entrance_pupil()
xp = systems.exit_pupil()
print(f"    入射光瞳: 相对物面位置 {ep['position']*1e3:.2f} mm（向左为正，负值=在物面右侧）, "
      f"直径 {ep['diameter']*1e3:.2f} mm")
print(f"    出射光瞳: 相对最后一面位置 {xp['position']*1e3:.2f} mm（向右为正）, "
      f"直径 {xp['diameter']*1e3:.2f} mm")
# 独立校验：入射光瞳半径 / 物到入射光瞳的距离 == 孔径光阑的物方孔径角
u_from_pupil = (ep["diameter"] / 2) / abs(ep["position"])
check("物方孔径角 = 入射光瞳半径 / 物到入射光瞳距离",
      u_from_pupil, [d["u_object"] for d in data if d["index"] == stop][0], tol=1e-12)
check("入射光瞳直径 = 光阑直径 x 2.5", ep["diameter"], 0.05)

print()
print("=" * 78)
print(f"全部 {PASS} 项自检通过。公式与仿真一致。")
print("=" * 78)
