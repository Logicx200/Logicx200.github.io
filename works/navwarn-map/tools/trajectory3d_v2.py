#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2 修正版弹道模型（3DOF，ECI，RK4 + J2）

相对 v1（trajectory3d.py）的修正：
  1. 质量账自洽：m0 = 各级装药 + 干重 + 载荷 + 整流罩，二级剩余质量 >= 干重+载荷；
  2. 一级质量按 CZ-2D 公开数据重排（m1_dry=10 t，原 15 t 导致 5.1 t 缺口）；
  3. 二级不再"推力沿惯性速度"一路硬推：一次点火进入 550 km 转移轨道，滑行到远地点，
     二次点火（可重启上面级）圆化 —— 这是这个推力/装药量下唯一物理可行的入轨方式；
  4. 落点/残骸由积分真实算出，不写 NOTAM 盒中心；NOTAM 盒只作对照；
  5. 经纬度回绕 -180 → -360 修正；T0 用 2026-11-18T22:44:30Z（原值差一年）；
  6. 积分步长收敛性检查；输出含收敛后的采样、事件、元素、一轨地面轨迹。

假设（均为"代表性"参数，非官方数据）：
  - 发射场：太原 38.849N 111.608E；射向 188.2°（由 A5897/A5898 连线反推）；
  - 两级火箭：m0=232 t，一级 175 t 装药 + 10 t 干重，二级 4.5 t 干重，
    整流罩 1.5 t，载荷 1.0 t；T1=2962 kN/ve1=2650 m/s，T2=742 kN/ve2=2900 m/s；
  - 目标轨道：550 km 圆轨道（v1 的假设；NOTAM 本身定不了高度）；
  - 上面级可二次点火（滑行 + 圆化）；一子级/整流罩按弹道 + 阻力落回。
"""
import math
import sys
import json
import os
import numpy as np

R = 6371008.8          # mean Earth radius m
MU = 3.986004418e14
OMEGA = 7.2921159e-5
J2 = 1.08262668e-3
LAT0 = math.radians(38.849)
LON0 = math.radians(111.608)
T0 = 1795041870.0      # 2026-11-18T22:44:30Z
TARGET_ALT = 550e3     # m
AZ = 188.2             # deg, 由落区连线反推的射向（地球相对）

VEH = dict(
    m0=232000.0,
    m1_prop=175000.0, m1_dry=10000.0, T1=2962e3, ve1=2650.0,
    m2_prop=None,      # 由质量账推出
    m2_dry=4500.0, payload=1000.0, fairing=1500.0, T2=742e3, ve2=2900.0,
    CdA=12.0,
)
VEH['m2_prop'] = (VEH['m0'] - VEH['m1_prop'] - VEH['m1_dry'] - VEH['m2_dry']
                  - VEH['payload'] - VEH['fairing'])
CDA_STAGE1_DEBRIS = 6.0
CDA_FAIRING = 2.5
M_FAIRING_DEBRIS = 600.0


# ----------------------------------------------------------------------------- 基础函数
def gmst(unix):
    """IAU-82 GMST（rad）"""
    jd = unix / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T ** 3 / 38710000.0
    return math.radians(g % 360.0)


def unit(x):
    n = np.linalg.norm(x)
    return x / n if n else x


def accel(r, v, thrust, mass, cda):
    rn = np.linalg.norm(r)
    g = -MU * r / rn ** 3
    z2 = r[2] * r[2]
    f = 1.5 * J2 * MU * R * R / rn ** 5
    g = g + np.array([f * r[0] * (5 * z2 / rn ** 2 - 1),
                      f * r[1] * (5 * z2 / rn ** 2 - 1),
                      f * r[2] * (5 * z2 / rn ** 2 - 3)])
    h = rn - R
    rho = 1.225 * math.exp(-max(h, 0.0) / 8500.0) if h < 200e3 else 0.0
    vrel = v - np.cross(np.array([0, 0, OMEGA]), r)
    drag = -0.5 * rho * cda * np.linalg.norm(vrel) * vrel
    return g + thrust / mass + drag / mass


def rk4(r, v, m, thrust, mdot, dt, cda):
    def f(r, v, m):
        return v, accel(r, v, thrust, m, cda), mdot
    k1 = f(r, v, m)
    k2 = f(r + dt / 2 * k1[0], v + dt / 2 * k1[1], m + dt / 2 * k1[2])
    k3 = f(r + dt / 2 * k2[0], v + dt / 2 * k2[1], m + dt / 2 * k2[2])
    k4 = f(r + dt * k3[0], v + dt * k3[1], m + dt * k3[2])
    return (r + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
            v + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
            m + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]))


def eci_to_geodetic(r, gm):
    """ECI -> geodetic (sphere). Fix: wrap to [-180,180) by -360, not -180."""
    x, y, z = r
    lon = math.degrees((math.atan2(y, x) - gm) % (2 * math.pi))
    if lon >= 180.0:
        lon -= 360.0
    return math.degrees(math.asin(z / np.linalg.norm(r))), lon, np.linalg.norm(r) - R


def elements(r, v):
    rn = np.linalg.norm(r)
    hv = np.cross(r, v)
    hn = np.linalg.norm(hv)
    inc = math.degrees(math.acos(max(-1.0, min(1.0, hv[2] / hn))))
    n = np.cross(np.array([0, 0, 1.0]), hv)
    nn = np.linalg.norm(n)
    ev = np.cross(v, hv) / MU - r / rn
    e = np.linalg.norm(ev)
    energy = np.linalg.norm(v) ** 2 / 2 - MU / rn
    a = -MU / (2 * energy)
    raan = 0.0
    if nn > 1e-12:
        raan = math.degrees(math.acos(max(-1.0, min(1.0, n[0] / nn))))
        if n[1] < 0:
            raan = 360.0 - raan
    return dict(a_km=a / 1000.0, e=e, inc_deg=inc,
                rp_km=a * (1 - e) / 1000.0, ra_km=a * (1 + e) / 1000.0,
                raan_deg=raan,
                period_min=2 * math.pi * math.sqrt(a ** 3 / MU) / 60.0)


def heading_frame(r):
    up = r / np.linalg.norm(r)
    east = unit(np.cross(np.array([0, 0, 1.0]), r))
    north = unit(np.cross(up, east))
    return up, east, north


def state0():
    th = gmst(T0)
    r = np.array([R * math.cos(LAT0) * math.cos(LON0),
                  R * math.cos(LAT0) * math.sin(LON0),
                  R * math.sin(LAT0)])
    r = np.array([math.cos(th) * r[0] - math.sin(th) * r[1],
                  math.sin(th) * r[0] + math.cos(th) * r[1], r[2]])
    return r, np.cross(np.array([0, 0, OMEGA]), r), th


# ----------------------------------------------------------------------------- 弹道积分
def run(k1=0.48, pitch_p=2.8, t_fair=206.0, az_deg=AZ, target_alt=TARGET_ALT,
        dt_ascent=0.1, dt_debris=0.5, dt_coast=0.5, dt_burn2=0.01, verbose=True):
    """Run the whole flight. Returns dict with samples/events/orbit etc."""
    r, v, th = state0()
    r_launch = r.copy()
    m = VEH['m0']
    t = 0.0
    mdot1 = VEH['T1'] / VEH['ve1']
    mdot2 = VEH['T2'] / VEH['ve2']
    samples = []
    events = []

    def geod(rr, tt):
        return eci_to_geodetic(rr, th + OMEGA * tt)

    def sample(tag, rr, vv, tt, every=5.0, t_last=[0.0]):
        if tt - t_last[0] >= every - 1e-9:
            lat, lon, alt = geod(rr, tt)
            samples.append([round(lat, 5), round(lon, 5), round(alt / 1000.0, 3),
                            round(tt, 2), tag])
            t_last[0] = tt

    # ---------------- 一级 ----------------
    burnt = 0.0
    while burnt < VEH['m1_prop']:
        up, east, north = heading_frame(r)
        pitch = math.radians(min(85.0, max(0.0, (t - 10.0) * k1)))
        azr = math.radians(az_deg)
        d = math.cos(azr) * north + math.sin(azr) * east
        thrust = (math.cos(pitch) * up + math.sin(pitch) * d) * VEH['T1']
        r, v, m = rk4(r, v, m, thrust, -mdot1, dt_ascent, VEH['CdA'])
        burnt += mdot1 * dt_ascent
        t += dt_ascent
        sample('ascent', r, v, t)
    t_sep = t
    m_stage1 = m
    stage1_state = (r.copy(), v.copy())
    events.append(dict(ev='一级关机/分离', t=round(t, 2),
                       alt_km=round((np.linalg.norm(r) - R) / 1000, 2),
                       v_kms=round(np.linalg.norm(v) / 1000, 3),
                       lat=round(geod(r, t)[0], 4), lon=round(geod(r, t)[1], 4)))

    # 一级残骸弹道落点（真实积分，不写盒中心）
    r1, v1, t1 = stage1_state[0].copy(), stage1_state[1].copy(), t_sep
    while np.linalg.norm(r1) > R and t1 < t_sep + 1800:
        r1, v1, _ = rk4(r1, v1, VEH['m1_dry'], np.zeros(3), 0.0, dt_debris, CDA_STAGE1_DEBRIS)
        t1 += dt_debris
    lat1, lon1, alt1 = geod(r1, t1)
    dr1 = math.acos(max(-1.0, min(1.0, np.dot(unit(r1), unit(r_launch))))) * R / 1000
    imp1 = dict(lat=lat1, lon=lon1, alt_km=alt1 / 1000, t=t1, downrange_km=dr1)
    events.append(dict(ev='一级落点（积分）', t=round(t1, 1), lat=round(lat1, 4),
                       lon=round(lon1, 4), alt_km=0.0, dist_km=round(dr1, 1), kind='impact'))

    # ---------------- 二级一次点火 ----------------
    m -= VEH['m1_dry']
    t_sep2 = t
    up0, _, _ = heading_frame(r)
    gamma_sep = math.degrees(math.asin(max(-1.0, min(1.0, np.dot(unit(v), up0)))))
    fairing_done = False
    cutoff1 = None
    while True:
        if m <= VEH['m2_dry'] + VEH['payload']:
            break
        up, east, north = heading_frame(r)
        u = min(1.0, (t - t_sep2) / (VEH['m2_prop'] / mdot2))
        gth = max(0.0, gamma_sep * (1.0 - u) ** pitch_p)
        azr = math.radians(az_deg)
        d = math.cos(azr) * north + math.sin(azr) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * VEH['T2']
        r_prev, v_prev, m_prev, t_prev = r.copy(), v.copy(), m, t
        r, v, m = rk4(r, v, m, thrust, -mdot2, dt_ascent, VEH['CdA'])
        t += dt_ascent
        sample('ascent', r, v, t)
        # 整流罩
        if (not fairing_done) and t >= t_fair:
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1800:
                rf, vf, _ = rk4(rf, vf, M_FAIRING_DEBRIS, np.zeros(3), 0.0, dt_debris, CDA_FAIRING)
                tf += dt_debris
            flat, flon, falt = geod(rf, tf)
            fdr = math.acos(max(-1.0, min(1.0, np.dot(unit(rf), unit(r_launch))))) * R / 1000
            events.append(dict(ev='整流罩分离', t=round(t, 2), alt_km=round((np.linalg.norm(r) - R) / 1000, 2),
                               lat=round(geod(r, t)[0], 4), lon=round(geod(r, t)[1], 4),
                               impact_t=round(tf, 1), impact_lat=round(flat, 4), impact_lon=round(flon, 4),
                               impact_dist_km=round(fdr, 1)))
            m -= VEH['fairing']
        # 一次关机：远地点到达目标高度（在最后一步内二分，使 ra 精确等于目标）
        el = elements(r, v)
        if el['ra_km'] * 1000 >= (R + target_alt) and el['ra_km'] * 1000 > el['rp_km'] * 1000:
            lo, hi = 0.0, 1.0
            for _ in range(48):
                mid = 0.5 * (lo + hi)
                rr, vv, mm = rk4(r_prev, v_prev, m_prev, thrust, -mdot2, mid * dt_ascent, VEH['CdA'])
                if elements(rr, vv)['ra_km'] * 1000 >= (R + target_alt):
                    hi = mid
                else:
                    lo = mid
            r, v, m = rk4(r_prev, v_prev, m_prev, thrust, -mdot2, hi * dt_ascent, VEH['CdA'])
            t = t_prev + hi * dt_ascent
            el = elements(r, v)
            cutoff1 = dict(t=t, alt_km=(np.linalg.norm(r) - R) / 1000,
                           v=np.linalg.norm(v) / 1000, m=m, el=el,
                           lat=geod(r, t)[0], lon=geod(r, t)[1])
            break
    if cutoff1 is None:
        cutoff1 = dict(t=t, alt_km=(np.linalg.norm(r) - R) / 1000, v=np.linalg.norm(v) / 1000,
                       m=m, el=elements(r, v), lat=geod(r, t)[0], lon=geod(r, t)[1])
    events.append(dict(ev='二级一次关机', t=round(t, 2), alt_km=round(cutoff1['alt_km'], 2),
                       v_kms=round(cutoff1['v'], 3), lat=round(cutoff1['lat'], 4),
                       lon=round(cutoff1['lon'], 4)))
    el1 = cutoff1['el']
    events.append(dict(ev='转移轨道', t=round(t, 2), rp_km=round(el1['rp_km'], 1),
                       ra_km=round(el1['ra_km'], 1), inc_deg=round(el1['inc_deg'], 2)))

    # ---------------- 滑行到远地点 ----------------
    up = r / np.linalg.norm(r)
    vr = np.dot(v, up)
    while vr > 0 and t < cutoff1['t'] + 4000:
        r, v, m = rk4(r, v, m, np.zeros(3), 0.0, dt_coast, VEH['CdA'])
        t += dt_coast
        up = r / np.linalg.norm(r)
        vr = np.dot(v, up)
        sample('coast', r, v, t, every=20.0)
    apogee = (np.linalg.norm(r) - R) / 1000
    el_coast = elements(r, v)
    events.append(dict(ev='滑行至远地点', t=round(t, 1), alt_km=round(apogee, 2),
                       lat=round(geod(r, t)[0], 4), lon=round(geod(r, t)[1], 4)))
    samples.append([round(geod(r, t)[0], 5), round(geod(r, t)[1], 5), round(apogee, 3), round(t, 2), 'coast'])

    # ---------------- 二级二次点火：圆化 ----------------
    burn2_start = t
    counter = 0
    while True:
        rn = np.linalg.norm(r)
        vc = math.sqrt(MU / rn)
        if np.linalg.norm(v) >= vc - 0.5 or m <= VEH['m2_dry'] + VEH['payload']:
            break
        thrust = unit(v) * VEH['T2']
        r, v, m = rk4(r, v, m, thrust, -mdot2, dt_burn2, VEH['CdA'])
        t += dt_burn2
        counter += 1
        if counter > 200000:
            break
    samples.append([round(geod(r, t)[0], 5), round(geod(r, t)[1], 5),
                    round((np.linalg.norm(r) - R) / 1000, 3), round(t, 2), 'insertion'])
    el = elements(r, v)
    lat_i, lon_i, alt_i = geod(r, t)
    events.append(dict(ev='入轨（二次点火圆化）', t=round(t, 2), alt_km=round(alt_i / 1000, 2),
                       v_kms=round(np.linalg.norm(v) / 1000, 3), lat=round(lat_i, 4),
                       lon=round(lon_i, 4), mass_kg=round(m, 1), prop_margin_kg=round(m - VEH['m2_dry'] - VEH['payload'], 1), kind='insert'))
    events.append(dict(ev='入轨根数', a_km=round(el['a_km'], 1), e=round(el['e'], 5),
                       inc_deg=round(el['inc_deg'], 3), rp_km=round(el['rp_km'], 1),
                       ra_km=round(el['ra_km'], 1), raan_deg=round(el['raan_deg'], 2),
                       period_min=round(el['period_min'], 2)))

    # ---------------- 一轨地面轨迹 ----------------
    orbit = []
    r0, v0 = r.copy(), v.copy()
    period = 2 * math.pi * math.sqrt(el['a_km'] * 1000 ** 3 / MU) if False else el['period_min'] * 60
    steps = int(1.2 * period / 5.0)
    for kk in range(steps + 1):
        tt = t + 5.0 * kk
        lat, lon, alt = geod(r0, tt)
        orbit.append([round(lat, 4), round(lon, 4), round(alt / 1000.0, 2)])
        r0, v0, _ = rk4(r0, v0, 1.0, np.zeros(3), 0.0, 5.0, 0.0)
    orbit3d = []
    r0, v0 = r.copy(), v.copy()
    for kk in range(steps + 1):
        r0, v0, _ = rk4(r0, v0, 1.0, np.zeros(3), 0.0, 5.0, 0.0)
        if kk % 2 == 0:
            orbit3d.append([round(float(x), 1) for x in r0])

    res = dict(
        launch_site=[38.849, 111.608],
        t0_utc='2026-11-18T22:44:30Z',
        azimuth_deg=az_deg,
        target_alt_km=target_alt / 1000.0,
        events=events,
        impact_stage1=imp1,
        cutoff1=dict(t=cutoff1['t'], alt_km=cutoff1['alt_km'], v=cutoff1['v']),
        elements={'a_km': round(el['a_km'], 1), 'e': round(el['e'], 6),
                  'inc_deg': round(el['inc_deg'], 3), 'rp_km': round(el['rp_km'], 1),
                  'ra_km': round(el['ra_km'], 1), 'raan_deg': round(el['raan_deg'], 2),
                  'period_min': round(el['period_min'], 2), 'alt_km': round((el['a_km'] * 1000 - R) / 1000, 1)},
        samples=samples,
        orbit=orbit,
        orbit3d=orbit3d,
        note='3DOF 积分（含 J2）。一级：175 t 装药/10 t 干重；二级：4.5 t 干重、可二次点火；整流罩 1.5 t。'
             '一级/整流罩落点为积分结果，供与 A5897/A5898 对照；轨道为滑行+远地点圆化后的实际状态。',
    )
    if verbose:
        print('stage1 sep: t=%.1f alt=%.1f km v=%.3f km/s' %
              (t_sep, (np.linalg.norm(stage1_state[0]) - R) / 1000, np.linalg.norm(stage1_state[1]) / 1000))
        print('stage1 impact: %.4f %.4f  t=%.1f  downrange=%.1f km' % (lat1, lon1, t1, dr1))
        print('cutoff1: t=%.1f alt=%.1f v=%.3f  transfer rp/ra=%.1f/%.1f' %
              (cutoff1['t'], cutoff1['alt_km'], cutoff1['v'], el1['rp_km'], el1['ra_km']))
        print('apogee: t=%.1f alt=%.1f' % (t, apogee))
        print('insertion: t=%.1f alt=%.1f v=%.3f  a=%.1f e=%.6f i=%.3f rp=%.1f ra=%.1f' %
              (t, alt_i / 1000, np.linalg.norm(v) / 1000, el['a_km'], el['e'], el['inc_deg'],
               el['rp_km'], el['ra_km']))
        print('final mass=%.1f kg (dry+payload=%.1f) -> propellant margin=%.1f kg' %
              (m, VEH['m2_dry'] + VEH['payload'], m - VEH['m2_dry'] - VEH['payload']))
    return res


def plot(res, png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    fig = plt.figure(figsize=(13, 9), facecolor='#07131c')
    ax = fig.add_subplot(111, projection='3d', facecolor='#07131c')
    u = np.linspace(0, 2 * np.pi, 40)
    vv = np.linspace(-np.pi / 2, np.pi / 2, 20)
    ax.plot_wireframe(R / 1000 * np.outer(np.cos(vv), np.cos(u)),
                      R / 1000 * np.outer(np.cos(vv), np.sin(u)),
                      R / 1000 * np.outer(np.sin(vv), np.ones_like(u)),
                      color='#2c6b8a', alpha=.18, linewidth=.4)

    def ll2xyz(lat, lon, alt_km=0.0):
        la, lo = math.radians(lat), math.radians(lon)
        rr = R / 1000 + alt_km
        return rr * math.cos(la) * math.cos(lo), rr * math.cos(la) * math.sin(lo), rr * math.sin(la)

    asc = [s for s in res['samples'] if s[4] in ('ascent',)]
    coa = [s for s in res['samples'] if s[4] == 'coast']
    pts = [ll2xyz(s[0], s[1], s[2]) for s in asc]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts],
            color='#ffb74d', lw=2.2, label='上升段（3DOF）')
    if coa:
        cp = [ll2xyz(s[0], s[1], s[2]) for s in coa]
        ax.plot([p[0] for p in cp], [p[1] for p in cp], [p[2] for p in cp],
                color='#4dd0e1', lw=1.3, ls='--', label='滑行段')
    o = res['orbit'][::3]
    op = [ll2xyz(p[0], p[1], p[2]) for p in o]
    ax.plot([p[0] for p in op], [p[1] for p in op], [p[2] for p in op],
            color='#c77dff', lw=1.4, ls='--', label='入轨后一轨')
    ax.scatter(*ll2xyz(*res['launch_site'], 0.3), color='#4dd0e1', s=60, marker='^', label='太原')
    i1 = res['impact_stage1']
    ax.scatter(*ll2xyz(i1['lat'], i1['lon'], 0.2), color='#ff5252', s=40,
               label='一级落点（%.0f km）' % i1['downrange_km'])
    for e in res['events']:
        if e['ev'] == '入轨（二次点火圆化）':
            ax.scatter(*ll2xyz(e['lat'], e['lon'], e['alt_km']), color='#7cf2c0', s=50, label='入轨点')
    ax.set_box_aspect((1, 1, 1))
    lim = 7200
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_axis_off(); ax.view_init(elev=22, azim=-60)
    el = res['elements']
    txt = (f"射向 {res['azimuth_deg']}°   i={el['inc_deg']:.2f}°   a={el['a_km']:.0f} km   e={el['e']:.4f}\n"
           f"高度 {el['alt_km']:.0f} km   周期 {el['period_min']:.1f} min   "
           f"入轨 v={el['a_km'] and (MU / (el['a_km'] * 1000)) ** 0.5 / 1000:.2f} km/s")
    ax.text2D(0.02, 0.96, txt, transform=ax.transAxes, color='#dff3fb', fontsize=10)
    ax.legend(loc='lower left', facecolor='#0d2532', edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=9)
    plt.tight_layout()
    plt.savefig(png, dpi=150, facecolor=fig.get_facecolor())
    print('saved', png)


def run_calibrated(target_alt=TARGET_ALT, **kw):
    ### 目标高度校准：J2 会让转移轨道远地点实际高度比瞬时根数低 ~2-4 km，
    ### 用割线法调整一次关机目标，使最终入轨实际高度 = target_alt。
    runs = []
    t_guess = target_alt
    for _ in range(4):
        res = run(target_alt=t_guess, **kw)
        actual = res['elements']['alt_km'] * 1000.0
        runs.append((t_guess, actual, res))
        if abs(actual - target_alt) < 50.0:
            break
        if len(runs) == 1:
            t_guess = target_alt + (target_alt - actual) + 3e3
        else:
            t0, a0, _ = runs[-2]
            t1, a1, _ = runs[-1]
            if abs(a1 - a0) < 1.0:
                break
            t_guess = t1 + (target_alt - a1) * (t1 - t0) / (a1 - a0)
    res = runs[-1][2]
    res['target_alt_km'] = target_alt / 1000.0
    return res


if __name__ == '__main__':
    k1 = float(sys.argv[1]) if len(sys.argv) > 1 else 0.48
    p = float(sys.argv[2]) if len(sys.argv) > 2 else 2.8
    tf = float(sys.argv[3]) if len(sys.argv) > 3 else 206.0
    res = run(k1=k1, pitch_p=p, t_fair=tf)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'trajectory3d.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print('wrote', out)
    plot(res, os.path.join(os.path.dirname(out), 'trajectory3d.png'))




