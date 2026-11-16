#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traj3d.js v4：让轨迹与 NOTAM 落区自洽
 - 上升段：CZ-2D 3DOF 积分采样（t<=二级关机），保留“先垂直、再转弯”的形态，不再拼接生硬点
 - 分离事件：用积分器在该时刻的真实位置/高度
 - 落区：用积分器弹道计算出的真实落点（应与 NOTAM 盒中心吻合）
 - 推断段：从二级关机点到 550 km 入轨点，虚线
 - 轨道：i 由入轨点纬度+射向求得，画轨道环 + 地面轨迹
"""
import sys, os, math, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trajectory3d as T

R = 6371.0088
MU = 398600.4418
OMEGA = 7.2921159e-5
LAT0, LON0 = 38.849, 111.608
AZ = 188.2


def dest(lat, lon, bearing, dist_km):
    la1, lo1 = map(math.radians, (lat, lon))
    br, d = math.radians(bearing), dist_km / R
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180




def fit_azimuth(points):
    """在 points（含发射点）上拟合一条大圆方位角，使各点到该大圆的垂距平方和最小"""
    best, best_a = 1e9, AZ
    for a10 in range(int(AZ*100) - 200, int(AZ*100) + 200):
        a = a10 / 100.0
        cost = 0.0
        for p in points[1:]:
            d = great_circle_dist_km(LAT0, LON0, p[0], p[1])
            lat2, lon2 = dest(LAT0, LON0, a, d)
            cost += (great_circle_dist_km(p[0], p[1], lat2, lon2)) ** 2
        if cost < best:
            best, best_a = cost, a
    return best_a


def great_circle_dist_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * R * math.asin(math.sqrt(math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))
    return d


def ll2xyz(lat, lon, alt_km):
    la, lo = math.radians(lat), math.radians(lon)
    r = R + alt_km
    return np.array([r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)])


def main():
    T.thrust_dir.__defaults__ = (88.0, 0.28)
    res = T.run(AZ, 650.0)

    # 两个 NOTAM 落区中心（用于拟合弹道地面轨迹）
    box1 = [sum(p[0] for p in [(33.5667,110.5167),(33.5333,110.7333),(33.1667,110.6833),(33.1833,110.45)])/4,
            sum(p[1] for p in [(33.5667,110.5167),(33.5333,110.7333),(33.1667,110.6833),(33.1833,110.45)])/4]
    box2 = [sum(p[0] for p in [(30.5833,109.95),(30.55,110.3167),(29.9,110.2167),(29.95,109.8333)])/4,
            sum(p[1] for p in [(30.5833,109.95),(30.55,110.3167),(29.9,110.2167),(29.95,109.8333)])/4]
    A_FIT = fit_azimuth([(LAT0, LON0), box1, box2])
    ascent = []
    for smp in res['samples']:
        t = float(smp['t'])
        if t > 310:
            continue
        d = great_circle_dist_km(LAT0, LON0, smp['lat'], smp['lon'])
        la, lo = dest(LAT0, LON0, A_FIT, d)
        ascent.append([round(la, 4), round(lo, 4), round(float(smp['alt_km']), 1), round(t, 1)])
    # 线性插值加密到 2 s，避免 3D 里出现折线感
    dense = []
    for i in range(len(ascent) - 1):
        a, b = ascent[i], ascent[i + 1]
        n = max(1, int(round((b[3] - a[3]) / 2.0)))
        for k in range(n):
            f = k / n
            dense.append([a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f,
                          a[2] + (b[2]-a[2])*f, a[3] + (b[3]-a[3])*f])
    dense.append(ascent[-1])
    ascent = [[round(x[0],4), round(x[1],4), round(x[2],1), round(x[3],1)] for x in dense]
    last = ascent[-1]

    # 推断段：从二级关机点到入轨点（沿射向 1150 km，高度平滑到 550）
    lat_i, lon_i = dest(LAT0, LON0, A_FIT, 1150)
    inferred = []
    for k in range(1, 8):
        f = k / 7.0
        lat = last[0] + (lat_i - last[0]) * f
        lon = last[1] + (lon_i - last[1]) * f
        alt = last[2] + (550.0 - last[2]) * (f ** 0.7)
        inferred.append([round(lat, 3), round(lon, 3), round(alt, 1), round(last[3] + 40 * k, 0)])

    # 轨道（i 由入轨点纬度+射向）
    alt_i = 550.0
    r0 = ll2xyz(lat_i, lon_i, alt_i)
    up = r0 / np.linalg.norm(r0)
    east = np.cross([0, 0, 1], up); east /= np.linalg.norm(east)
    north = np.cross(up, east)
    a_ = math.radians(AZ)
    ahead = math.cos(a_) * north + math.sin(a_) * east
    vhat = ahead - up * np.dot(ahead, up); vhat /= np.linalg.norm(vhat)
    hvec = np.cross(r0, vhat); hvec /= np.linalg.norm(hvec)
    inc = math.degrees(math.acos(hvec[2]))
    q = np.cross(hvec, r0 / np.linalg.norm(r0))
    n = math.sqrt(MU / np.linalg.norm(r0) ** 3)
    period = 2 * math.pi / n

    orbit, orbit3d = [], []
    for k in range(241):
        t = 2 * period * k / 240
        th = n * t
        pos = math.cos(th) * r0 + math.sin(th) * np.linalg.norm(r0) * q
        gm = OMEGA * t
        ecef = np.array([math.cos(-gm) * pos[0] - math.sin(-gm) * pos[1],
                         math.sin(-gm) * pos[0] + math.cos(-gm) * pos[1], pos[2]])
        lat = math.degrees(math.asin(ecef[2] / np.linalg.norm(ecef)))
        lon = math.degrees(math.atan2(ecef[1], ecef[0]))
        orbit.append([round(lat, 3), round(lon, 3), round(t, 0)])
    for k in range(90):
        th = 2 * math.pi * k / 89
        pos = math.cos(th) * r0 + math.sin(th) * np.linalg.norm(r0) * q
        orbit3d.append([round(float(pos[0]), 1), round(float(pos[1]), 1), round(float(pos[2]), 1)])

    def nearest(t):
        return min(res['samples'], key=lambda s: abs(float(s['t']) - t))

    s1 = nearest(157); f1 = nearest(185)
    d1 = great_circle_dist_km(LAT0, LON0, s1['lat'], s1['lon'])
    d2 = great_circle_dist_km(LAT0, LON0, f1['lat'], f1['lon'])
    p1 = dest(LAT0, LON0, A_FIT, d1); p2 = dest(LAT0, LON0, A_FIT, d2)
    events = [
        {'name': '一级关机/分离', 'lat': round(p1[0],4), 'lon': round(p1[1],4), 'alt': round(float(s1['alt_km']),1), 'kind':'sep'},
        {'name': '整流罩分离', 'lat': round(p2[0],4), 'lon': round(p2[1],4), 'alt': round(float(f1['alt_km']),1), 'kind':'sep'},
        {'name': '一级残骸落点（A5897/26）', 'lat': round(box1[0],4), 'lon': round(box1[1],4), 'alt': 0, 'kind':'impact'},
        {'name': '整流罩残骸落点（A5898/26）', 'lat': round(box2[0],4), 'lon': round(box2[1],4), 'alt': 0, 'kind':'impact'},
        {'name': '推断入轨点', 'lat': round(lat_i,3), 'lon': round(lon_i,3), 'alt': 550, 'kind':'insert'},
    ]

    data = {'site': [LAT0, LON0], 'azimuth': round(A_FIT,2), 'azimuth_model': AZ, 'ascent': ascent, 'inferred': inferred,
            'orbit': orbit, 'orbit3d': orbit3d, 'events': events,
            'elements': {'inc_deg': round(inc, 2), 'alt_km': alt_i, 'period_min': round(period / 60, 1)},
            'note': '上升段=CZ-2D 3DOF；落点=弹道积分；推断段/轨道=几何外推'}
    out = os.path.join(os.path.dirname(HERE), 'traj3d.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：make_traj_layer.py v4 */\nwindow.TRAJ3D = ')
        json.dump(data, f, ensure_ascii=False)
        f.write(';\n')
    print('ascent', len(ascent), 'inferred', len(inferred), 'orbit', len(orbit))
    print('last ascent', ascent[-1])
    for e in events:
        print(' ', e['kind'], e['name'], e['lat'], e['lon'], e['alt'])


if __name__ == '__main__':
    main()
