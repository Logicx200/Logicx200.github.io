#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三维弹道/轨道模型（3DOF 点质量，ECI，RK4）

由太原发射场 + 落区连线方位角（188.2°）出发，给一套“代表性”两级火箭参数，
积分上升段 → 一级落点 → 二级入轨，输出：
  - 三维轨迹（lat/lon/alt/time/speed）
  - 一级/整流罩落点与航程
  - 入轨根数 (a, e, i, Ω, ω, ν, 周期)
  - 一轨地面轨迹
并画 3D 图。

说明：火箭型号未知，参数为“中型两级液氧煤油”代表值；结果用于量级/几何验证，
      不是该次任务真实弹道。

用法: python trajectory3d.py [方位角] [目标高度km]
"""
import math, json, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
from mpl_toolkits.mplot3d import Axes3D  # noqa

R = 6371.0088e3
MU = 3.986004418e14
OMEGA = 7.2921159e-5
J2 = 1.08262668e-3

LAT0 = math.radians(38.849)
LON0 = math.radians(111.608)

# 长征二号丁（CZ-2D）公开参数近似值：两级、四氧化二氮/偏二甲肼
# 起飞质量 232 t，一级 4×YF-20B（海平面 2962 kN），二级 YF-22E（真空 742 kN）
VEH = dict(
    m0=232000.0, m1_prop=175000.0, m1_dry=15000.0, T1=2962e3, ve1=2650.0,
    m2_prop=38000.0, m2_dry=4500.0, payload=3100.0, fairing=1500.0,
    T2=742e3, ve2=2900.0,
    CdA=12.0,
)


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n else v


def accel(r, v, thrust_vec, mass, CdA):
    rn = np.linalg.norm(r)
    g = -MU * r / rn ** 3
    # 大气阻力
    h = rn - R
    rho = 1.225 * math.exp(-max(h, 0) / 8500.0) if h < 200e3 else 0.0
    vrel = v - np.cross(np.array([0, 0, OMEGA]), r)
    drag = -0.5 * rho * CdA * np.linalg.norm(vrel) * vrel
    return g + (thrust_vec / mass if mass > 0 else 0) + drag / mass


def rk4(r, v, m, thrust_vec, mdotsign, CdA, dt):
    def f(r, v, m):
        return v, accel(r, v, thrust_vec, m, CdA), mdotsign
    k1r, k1v, k1m = f(r, v, m)
    k2r, k2v, k2m = f(r + dt / 2 * k1r, v + dt / 2 * k1v, m + dt / 2 * k1m)
    k3r, k3v, k3m = f(r + dt / 2 * k2r, v + dt / 2 * k2v, m + dt / 2 * k2m)
    k4r, k4v, k4m = f(r + dt * k3r, v + dt * k3v, m + dt * k3m)
    return (r + dt / 6 * (k1r + 2 * k2r + 2 * k3r + k4r),
            v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v),
            m + dt / 6 * (k1m + 2 * k2m + 2 * k3m + k4m))


def thrust_dir(t, r, d0, max_pitch=88.0, rate=0.30):
    up = unit(r)
    d = d0 - up * np.dot(d0, up)
    if np.linalg.norm(d) < 1e-9:
        return up
    d = unit(d)
    pitch = math.radians(min(max_pitch, max(0.0, (t - 10.0) * rate)))
    return math.cos(pitch) * up + math.sin(pitch) * d


def gmst(t0):
    jd = 2451545.0 + (t0 - 946728000.0) / 86400.0
    T = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T
    return math.radians(g % 360)


def eci_to_geodetic(r, gmst_angle):
    """ECI -> 经纬高（球面近似）"""
    x, y, z = r
    lon = (math.atan2(y, x) - gmst_angle + 4 * math.pi) % (2 * math.pi)
    lat = math.asin(z / np.linalg.norm(r))
    return math.degrees(lat), math.degrees(lon) - 180 if math.degrees(lon) > 180 else math.degrees(lon), np.linalg.norm(r) - R


def elements(r, v):
    rn = np.linalg.norm(r)
    h = np.cross(r, v)
    hn = np.linalg.norm(h)
    inc = math.degrees(math.acos(h[2] / hn))
    n = np.cross(np.array([0, 0, 1.0]), h)
    nn = np.linalg.norm(n)
    ev = np.cross(v, h) / MU - r / rn
    e = np.linalg.norm(ev)
    energy = np.linalg.norm(v) ** 2 / 2 - MU / rn
    a = -MU / (2 * energy)
    ra = a * (1 + e) if e < 1 else float('inf')
    rp = a * (1 - e) if e < 1 else a * (1 - e)
    period = 2 * math.pi * math.sqrt(a ** 3 / MU) if a > 0 else float('inf')
    raan = math.degrees(math.acos(max(-1, min(1, n[0] / nn)))) if nn else 0
    if n[1] < 0:
        raan = 360 - raan
    return dict(a_km=a / 1000, e=round(e, 6), inc_deg=round(inc, 3),
                raan_deg=round(raan, 2), rp_km=rp / 1000, ra_km=ra / 1000,
                period_min=round(period / 60, 2))


def run(az_deg=188.2, target_alt_km=550.0):
    t0 = 1763505870.0  # 2026-11-18T22:44:30Z
    th = gmst(t0)
    r0 = np.array([R * math.cos(LAT0) * math.cos(LON0),
                   R * math.cos(LAT0) * math.sin(LON0),
                   R * math.sin(LAT0)])
    r0 = np.array([math.cos(th) * r0[0] - math.sin(th) * r0[1],
                   math.sin(th) * r0[0] + math.cos(th) * r0[1], r0[2]])
    v0 = np.cross(np.array([0, 0, OMEGA]), r0)   # 随地球自转的初始东向速度
    az = math.radians(az_deg)

    # 发射方位单位向量（当地水平面）
    up = unit(r0)
    east = unit(np.cross(np.array([0, 0, 1.0]), r0))
    north = unit(np.cross(up, east))
    heading = math.cos(az) * north + math.sin(az) * east   # 方位角自北顺时针

    m = VEH['m0']
    r, v = r0.copy(), v0.copy()
    dt = 0.5
    t = 0.0
    samples = []
    events = []

    def log(tag):
        lat, lon, alt = eci_to_geodetic(r, th + OMEGA * t)
        samples.append(dict(t=round(t, 1), lat=round(lat, 5), lon=round(lon, 5),
                            alt_km=round(alt / 1000, 2), v_kms=round(np.linalg.norm(v) / 1000, 3),
                            phase=tag))

    # ---- 一级 ----
    mdot1 = VEH['T1'] / VEH['ve1']
    burnt1 = 0.0
    while burnt1 < VEH['m1_prop'] and (np.linalg.norm(r) - R) > -10.0:
        dirv = thrust_dir(t, r, heading)
        thrust = dirv * VEH['T1']
        r, v, m = rk4(r, v, m, thrust, -mdot1, VEH['CdA'], dt)
        burnt1 += mdot1 * dt
        t += dt
        if abs(t % 5) < dt:
            log('ascent1')
    events.append(dict(ev='一级关机/分离', t=round(t, 1), alt_km=round((np.linalg.norm(r) - R) / 1000, 1),
                       v_kms=round(np.linalg.norm(v) / 1000, 3), inc_deg=elements(r, v)['inc_deg']))
    m -= VEH['m1_dry']
    # 一级弹道落点
    m1_mass = VEH['m1_dry']
    r1, v1, t1 = r.copy(), v.copy(), t
    while np.linalg.norm(r1) > R and t1 < t + 900:
        r1, v1, _ = rk4(r1, v1, m1_mass, np.zeros(3), 0, 6.0, dt)
        t1 += dt
    lat, lon, _ = eci_to_geodetic(r1, th + OMEGA * t1)
    imp1 = dict(lat=round(lat, 4), lon=round(lon, 4), t=round(t1, 1),
                downrange_km=round(math.acos(min(1, np.dot(unit(r0), unit(r1)))) * R / 1000, 1))

    # ---- 二级 ----
    mdot2 = VEH['T2'] / VEH['ve2']
    burnt2 = 0.0
    fairing_done = False
    while burnt2 < VEH['m2_prop']:
        alt_now = np.linalg.norm(r) - R
        vr_now = np.dot(v, unit(r))
        if alt_now > target_alt_km * 1000 * 0.92 and vr_now <= 0:
            break
        dirv = unit(v)
        thrust = dirv * VEH['T2']
        r, v, m = rk4(r, v, m, thrust, -mdot2, VEH['CdA'], dt)
        burnt2 += mdot2 * dt
        t += dt
        if abs(t % 5) < dt:
            log('ascent2')
        if not fairing_done and t > 200:
            m -= VEH['fairing']
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1500:
                rf, vf, _ = rk4(rf, vf, 600.0, np.zeros(3), 0, 2.5, dt)
                tf += dt
            flat, flon, _ = eci_to_geodetic(rf, th + OMEGA * tf)
            fimp = dict(lat=round(flat, 4), lon=round(flon, 4), t=round(tf, 1),
                        downrange_km=round(math.acos(min(1, np.dot(unit(r0), unit(rf)))) * R / 1000, 1))
            events.append(dict(ev='整流罩分离', t=round(t, 1), alt_km=round((np.linalg.norm(r) - R) / 1000, 1),
                               impact=fimp))
    events.append(dict(ev='二级关机', t=round(t, 1), alt_km=round((np.linalg.norm(r) - R) / 1000, 1),
                       v_kms=round(np.linalg.norm(v) / 1000, 3), inc_deg=elements(r, v)['inc_deg']))

    # 滑行到目标高度附近（若尚未到达）
    while (np.linalg.norm(r) - R) / 1000 < target_alt_km and t < 3000:
        r, v, m = rk4(r, v, m, np.zeros(3), 0, VEH['CdA'], dt)
        t += dt
        if abs(t % 5) < dt:
            log('coast')
    el = elements(r, v)
    events.append(dict(ev='入轨', t=round(t, 1), alt_km=round((np.linalg.norm(r) - R) / 1000, 1),
                       v_kms=round(np.linalg.norm(v) / 1000, 3), elements=el))

    # ---- 一轨地面轨迹 ----
    orbit, tt = [], 0.0
    ro, vo = r.copy(), v.copy()
    while tt < 6000:
        ro, vo, _ = rk4(ro, vo, 1, np.zeros(3), 0, 0, 2.0)
        tt += 2
        lat, lon, alt = eci_to_geodetic(ro, th + OMEGA * (t + tt))
        orbit.append([round(lat, 3), round(lon, 3), round(alt / 1000, 1)])
    fimp = None
    for e in events:
        if e.get('impact'):
            fimp = e['impact']
    out = dict(launch_site=[math.degrees(LAT0), math.degrees(LON0)], azimuth=az_deg,
               impact_fairing=fimp,
               t0_utc='2026-11-18T22:44:30Z', target_alt_km=target_alt_km,
               events=events, impact1=imp1, elements=el,
               samples=samples[::2], orbit=orbit[::5])
    return out


def plot(res, png):
    fig = plt.figure(figsize=(13, 9), facecolor='#07131c')
    ax = fig.add_subplot(111, projection='3d', facecolor='#07131c')
    # 地球线框
    u = np.linspace(0, 2 * np.pi, 40)
    v = np.linspace(-np.pi / 2, np.pi / 2, 20)
    x = R / 1000 * np.outer(np.cos(v), np.cos(u))
    y = R / 1000 * np.outer(np.cos(v), np.sin(u))
    z = R / 1000 * np.outer(np.sin(v), np.ones_like(u))
    ax.plot_wireframe(x, y, z, color='#2c6b8a', alpha=.18, linewidth=.4)

    def ll2xyz(lat, lon, alt_km=0):
        la, lo = math.radians(lat), math.radians(lon)
        rr = R / 1000 + alt_km
        return rr * math.cos(la) * math.cos(lo), rr * math.cos(la) * math.sin(lo), rr * math.sin(la)

    pts = [ll2xyz(s['lat'], s['lon'], s['alt_km']) for s in res['samples']]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], color='#ffb74d', lw=2.2, label='上升段（3DOF 积分）')
    orb = [ll2xyz(o[0], o[1], o[2]) for o in res['orbit']]
    ax.plot([p[0] for p in orb], [p[1] for p in orb], [p[2] for p in orb], color='#c77dff', lw=1.4, ls='--', label='入轨后一轨')

    ls = ll2xyz(*res['launch_site'], 0.3)
    ax.scatter(*ls, color='#4dd0e1', s=60, marker='^', label='太原')
    i1 = res['impact1']
    p1 = ll2xyz(i1['lat'], i1['lon'], 0.2)
    ax.scatter(*p1, color='#ff5252', s=40, label=f"一级落点（{i1['downrange_km']} km）")
    ax.set_box_aspect((1, 1, 1))
    lim = 7200
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_axis_off()
    ax.view_init(elev=22, azim=-60)
    el = res['elements']
    txt = (f"方位角 {res['azimuth']}°   i={el['inc_deg']:.2f}°   {el['a_km']:.0f}×{el['rp_km']:.0f}/{el['ra_km']:.0f} km\n"
           f"e={el['e']:.4f}   周期 {el['period_min']:.1f} min   入轨 v={res['events'][-1]['v_kms']:.2f} km/s")
    ax.text2D(0.02, 0.96, txt, transform=ax.transAxes, color='#dff3fb', fontsize=10)
    ax.legend(loc='lower left', facecolor='#0d2532', edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=9)
    plt.tight_layout()
    plt.savefig(png, dpi=150, facecolor=fig.get_facecolor())
    print('saved', png)


if __name__ == '__main__':
    az = float(sys.argv[1]) if len(sys.argv) > 1 else 188.2
    alt = float(sys.argv[2]) if len(sys.argv) > 2 else 550.0
    res = run(az, alt)
    json.dump(res, open('trajectory3d.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for e in res['events']:
        print(e)
    print('impact1', res['impact1'])
    print('elements', res['elements'])
    plot(res, 'trajectory3d.png')
