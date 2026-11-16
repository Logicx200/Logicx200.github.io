#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从“发射场 + 落区连线方位角”估算轨道参数（能算什么、不能算什么）。

输入：trajectory.js（launch_window.py 生成）或命令行给的 纬度/方位角
输出：
  - 轨道倾角 i = arccos(cos φ · sin A)
  - 若为太阳同步轨道（SSO），由 i 反解所需高度（J2 进动模型）
  - 方位角不确定度 → 倾角/高度/横向偏差的传播
  - 前 1000 km 的地面轨迹采样点（大圆）
说明：NOTAM 不含速度与各级落区时刻，因此只能定“轨道平面（倾角/射向）”，
      不能定半长轴/偏心率/近地点——那需要 T0 精确值 + 落区时刻 + 弹道模型或 TLE。
"""
import json, math, sys, os

mu = 398600.4418
Re = 6378.137
J2 = 1.08262668e-3
DAY = 86400.0


def inc_from_az(lat_deg, az_deg):
    return math.degrees(math.acos(math.cos(math.radians(lat_deg)) * math.sin(math.radians(az_deg))))


def az_from_inc(lat_deg, inc_deg):
    x = math.cos(math.radians(inc_deg)) / math.cos(math.radians(lat_deg))
    a = math.degrees(math.asin(x))       # 可能为负（顺行/逆行）
    return (180.0 - a) % 360.0 if x < 0 else a


def sso_alt(inc_deg):
    target = math.radians(360 / 365.2422) / DAY
    lo, hi = 6500.0, 9000.0
    for _ in range(80):
        a = (lo + hi) / 2
        n = math.sqrt(mu / a ** 3)
        om = -1.5 * n * J2 * (Re / a) ** 2 * math.cos(math.radians(inc_deg))
        if om > target:
            lo = a
        else:
            hi = a
    return (lo + hi) / 2 - Re


def dest(lat, lon, bearing, dist_km):
    la1, lo1 = map(math.radians, (lat, lon))
    br, d = math.radians(bearing), dist_km / 6371.0088
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180


def main(traj_path):
    raw = open(traj_path, encoding='utf-8-sig').read()
    i0, i1 = raw.find('{'), raw.rfind('}')
    T = json.loads(raw[i0:i1+1])
    lat = T['site']['ll'][0]
    az = T['bearing_deg']
    print(f"发射场 {T['site']['name']}（{lat:.3f}N），落区连线方位角 {az:.1f}°")
    i = inc_from_az(lat, az)
    print(f"→ 轨道倾角 i = arccos(cosφ·sinA) = {i:.2f}°")
    print(f"   若为太阳同步轨道：对应高度 ≈ {sso_alt(i):.0f} km（偏低则说明落区中心相对理论轨迹有横向偏移）")
    print("   典型 SSO 反查：")
    for alt_i in (97.0, 97.4, 97.8, 98.2):
        print(f"     i={alt_i:.1f}° → 需要射向 {az_from_inc(lat, alt_i):.2f}°，SSO 高度 {sso_alt(alt_i):.0f} km")
    print("   方位角不确定度传播（±ΔA）:")
    for dA in (0.5, 1.0, 1.5):
        i2 = inc_from_az(lat, az + dA)
        print(f"     ±{dA:.1f}° → 倾角 {i:.2f}–{i2:.2f}°，横向 {617*math.sin(math.radians(dA)):.0f} km@617km，SSO 高度差 ≈ {sso_alt(i2)-sso_alt(i):+.0f} km")
    print("   前 1000 km 地面轨迹采样：")
    for d in (200, 400, 600, 800, 1000):
        la, lo = dest(lat, T['site']['ll'][1], az, d)
        print(f"     +{d:4d} km → {la:.3f}N {lo:.3f}E")
    print("   注：只能定轨道平面；速度/半长轴/偏心率/近地点需 T0 + 各级落区时刻 + 弹道模型或 TLE。")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'trajectory.js')
