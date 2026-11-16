#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三维轨道/弹道几何模型（不依赖未知的火箭参数）

输入约束（来自两条 NOTAM + 本轮推断）：
  - 发射场：太原 38.849N 111.608E
  - 射向：188.2°（落区连线；若按 SSO 500–700 km，实际约 189.5–190.5°）
  - 一级落区：沿射向 ~617 km；二级/整流罩落区：~967 km
  - 目标轨道：太阳同步、高度 550 km（可调）

模型给的是“轨道平面 + 地面轨迹 + 高度剖面”的几何解，不是飞行力学解：
上升段按距离给出经验高度剖面，入轨后是倾角 i=arccos(cosφ·sinA) 的圆轨道。
"""
import math, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

R = 6371.0088
MU = 398600.4418
LAT0, LON0 = 38.849, 111.608
AZ = 188.2
ALT_KM = 550.0


def dest(lat, lon, bearing, dist_km):
    la1, lo1 = map(math.radians, (lat, lon))
    br, d = math.radians(bearing), dist_km / R
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180


def ll2xyz(lat, lon, alt_km=0.0):
    la, lo = math.radians(lat), math.radians(lon)
    r = R + alt_km
    return r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)


def build():
    # 上升段：距离-高度经验剖面（km）
    prof_s = [0, 50, 120, 200, 300, 420, 520, 620, 720, 820, 920, 1040, 1150]
    prof_h = [0, 3, 9, 18, 33, 48, 60, 68, 90, 150, 250, 420, 550]
    s_max = 1150
    ascent = []
    for s in range(0, s_max + 1, 10):
        h = float(np.interp(s, prof_s, prof_h))
        lat, lon = dest(LAT0, LON0, AZ, s)
        ascent.append((lat, lon, h, s, h / 0.09 if s > 620 else None))  # 粗估速度略
    # 入轨点
    lat_i, lon_i = dest(LAT0, LON0, AZ, s_max)
    # 轨道面法向：由入轨点位置与射向确定
    p = np.array(ll2xyz(lat_i, lon_i, ALT_KM))
    up = p / np.linalg.norm(p)
    east = np.cross([0, 0, 1], up); east /= np.linalg.norm(east)
    north = np.cross(up, east)
    ahead = math.cos(math.radians(AZ)) * north + math.sin(math.radians(AZ)) * east
    v_hat = ahead - up * np.dot(ahead, up); v_hat /= np.linalg.norm(v_hat)
    h = np.cross(p, v_hat); h /= np.linalg.norm(h)
    inc = math.degrees(math.acos(h[2]))
    a = R + ALT_KM
    v_orb = math.sqrt(MU / a)
    period = 2 * math.pi * math.sqrt(a ** 3 / MU)
    q = np.cross(h, p / np.linalg.norm(p))
    orbit = []
    for deg in range(0, 361, 2):
        th = math.radians(deg)
        pt = a * (np.cos(th) * (p / np.linalg.norm(p)) + np.sin(th) * q)
        orbit.append(tuple(pt))
    # 落区中心
    ring1 = [[33.5667, 110.5167], [33.5333, 110.7333], [33.1667, 110.6833], [33.1833, 110.45]]
    ring2 = [[30.5833, 109.95], [30.55, 110.3167], [29.9, 110.2167], [29.95, 109.8333]]
    imp = [(ring1, 'A5897/26'), (ring2, 'A5898/26')]
    return dict(ascent=ascent, orbit=orbit, inc=inc, a=a, v_orb=v_orb, period=period,
                lat_i=lat_i, lon_i=lon_i, imp=imp)




def enu(lat, lon, alt_km=0.0, lat0=LAT0, lon0=LON0):
    la, lo = math.radians(lat), math.radians(lon)
    r = R + alt_km
    x = r * math.cos(la) * math.cos(lo); y = r * math.cos(la) * math.sin(lo); z = r * math.sin(la)
    la0, lo0 = math.radians(lat0), math.radians(lon0)
    r0 = R
    x0 = r0 * math.cos(la0) * math.cos(lo0); y0 = r0 * math.cos(la0) * math.sin(lo0); z0 = r0 * math.sin(la0)
    dx, dy, dz = x - x0, y - y0, z - z0
    e = -math.sin(lo0) * dx + math.cos(lo0) * dy
    n = -math.sin(la0) * math.cos(lo0) * dx - math.sin(la0) * math.sin(lo0) * dy + math.cos(la0) * dz
    u = math.cos(la0) * math.cos(lo0) * dx + math.cos(la0) * math.sin(lo0) * dy + math.sin(la0) * dz
    return e, n, u


def plot2(m, png='orbit3d.png'):
    fig = plt.figure(figsize=(16, 8.6), facecolor='#07131c')
    # ---- 左：全球视角 ----
    ax = fig.add_subplot(121, projection='3d', facecolor='#07131c')
    u = np.linspace(0, 2 * np.pi, 48); v = np.linspace(-np.pi / 2, np.pi / 2, 24)
    ax.plot_surface(R * np.outer(np.cos(v), np.cos(u)), R * np.outer(np.cos(v), np.sin(u)),
                    R * np.outer(np.sin(v), np.ones_like(u)), color='#12455e', alpha=.30, linewidth=0, shade=True)
    ax.plot(*zip(*m['orbit']), color='#c77dff', lw=1.6, ls='--', label=f"轨道 i={m['inc']:.2f}°")
    asc = [ll2xyz(a[0], a[1], max(a[2], 8)) for a in m['ascent']]
    ax.plot(*zip(*asc), color='#ffb74d', lw=2.4, label='上升段')
    ax.scatter(*ll2xyz(LAT0, LON0, 30), color='#4dd0e1', s=70, marker='^', label='太原')
    ax.set_box_aspect((1, 1, 1)); lim = 7200
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_axis_off(); ax.view_init(elev=24, azim=-58)
    ax.text2D(0.02, 0.98, '全球视角：轨道面', transform=ax.transAxes, color='#9fc6da', fontsize=10)
    ax.legend(loc='lower left', facecolor='#0d2532', edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=8)

    # ---- 右：发射走廊 3D（东-北-天） ----
    ax2 = fig.add_subplot(122, projection='3d', facecolor='#07131c')
    tr = [enu(a[0], a[1], a[2]) for a in m['ascent']]
    ax2.plot(*zip(*tr), color='#ffb74d', lw=2.6, label='上升段')
    # 地面轨迹投影
    ax2.plot([t[0] for t in tr], [t[1] for t in tr], [0] * len(tr), color='#4dd0e1', lw=1, ls=':')
    # 落区
    for ring, name in m['imp']:
        pts = [enu(p[0], p[1], 0) for p in ring]
        ax2.plot([q[0] for q in pts] + [pts[0][0]], [q[1] for q in pts] + [pts[0][1]], [0] * (len(pts) + 1), color='#ff5252', lw=1.6)
    # 入轨段（前 25°）
    seg = m['orbit'][:6]
    segll = []
    for pt in seg:
        rr = np.linalg.norm(pt)
        lat = math.degrees(math.asin(pt[2] / rr)); lon = math.degrees(math.atan2(pt[1], pt[0]))
        segll.append(enu(lat, lon, rr - R))
    ax2.plot(*zip(*segll), color='#c77dff', lw=1.8, ls='--', label='入轨后')
    for axis in (ax2.xaxis, ax2.yaxis, ax2.zaxis):
        axis.set_pane_color((0.03, 0.08, 0.11, 1.0))
        axis.line.set_color('#2c6b8a')
    ax2.grid(color='#1d4459')
    ax2.set_xlabel('东 (km)', color='#9fc6da'); ax2.set_ylabel('北 (km)', color='#9fc6da'); ax2.set_zlabel('高度 (km)', color='#9fc6da')
    ax2.tick_params(colors='#7d95a2', labelsize=7)
    ax2.set_xlim(-700, 700); ax2.set_ylim(-1400, 100); ax2.set_zlim(0, 750)
    ax2.view_init(elev=20, azim=-125)
    ax2.text2D(0.02, 0.98, '发射走廊：东-北-天坐标', transform=ax2.transAxes, color='#9fc6da', fontsize=10)
    ax2.legend(loc='upper right', facecolor='#0d2532', edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=8)

    fig.suptitle(f"太原 → SSO 三维模型（几何解）  i={m['inc']:.2f}°  h={ALT_KM:.0f} km  T={m['period']/60:.1f} min  v={m['v_orb']:.2f} km/s",
                 color='#dff3fb', fontsize=12, y=0.95)
    plt.tight_layout()
    plt.savefig(png, dpi=150, facecolor=fig.get_facecolor())
    print('saved', png)

def plot(m, png='orbit3d.png'):
    fig = plt.figure(figsize=(13, 9.5), facecolor='#07131c')
    ax = fig.add_subplot(111, projection='3d', facecolor='#07131c')
    u = np.linspace(0, 2 * np.pi, 48); v = np.linspace(-np.pi / 2, np.pi / 2, 24)
    ax.plot_surface(R * np.outer(np.cos(v), np.cos(u)), R * np.outer(np.cos(v), np.sin(u)),
                    R * np.outer(np.sin(v), np.ones_like(u)), color='#12455e', alpha=.35,
                    linewidth=0, shade=True)
    # 经纬网
    for lon in range(0, 360, 30):
        la = np.linspace(-80, 80, 40) * math.pi / 180
        lo = math.radians(lon)
        ax.plot(R * np.cos(la) * math.cos(lo), R * np.cos(la) * math.sin(lo), R * np.sin(la),
                color='#2c6b8a', lw=.3, alpha=.5)
    # 上升段
    asc = [ll2xyz(a[0], a[1], a[2]) for a in m['ascent']]
    ax.plot(*zip(*asc), color='#ffb74d', lw=2.6, label='上升段（经验高度剖面）')
    # 轨道
    ax.plot(*zip(*m['orbit']), color='#c77dff', lw=1.8, ls='--', label=f"入轨轨道 i={m['inc']:.2f}°")
    # 标记
    ax.scatter(*ll2xyz(LAT0, LON0), color='#4dd0e1', s=60, marker='^', label='太原')
    ax.scatter(*ll2xyz(m['lat_i'], m['lon_i'], ALT_KM), color='#7cf2c0', s=40, label='入轨点')
    for ring, name in m['imp']:
        ax.scatter(*ll2xyz(ring[0][0], ring[0][1], 10), color='#ff5252', s=26)
    ax.set_box_aspect((1, 1, 1)); lim = 7300
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_axis_off(); ax.view_init(elev=20, azim=-62)
    ax.text2D(0.02, 0.97,
              f"i={m['inc']:.2f}°   a={m['a']:.0f} km (h={ALT_KM:.0f} km)   周期 {m['period']/60:.1f} min   v={m['v_orb']:.2f} km/s\n"
              f"射向 {AZ}°（落区连线）  一级落区 617 km  二级落区 967 km",
              transform=ax.transAxes, color='#dff3fb', fontsize=10)
    ax.legend(loc='lower left', facecolor='#0d2532', edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=9)
    plt.tight_layout()
    plt.savefig(png, dpi=150, facecolor=fig.get_facecolor())
    print('saved', png)


if __name__ == '__main__':
    m = build()
    json.dump({k: v for k, v in m.items() if k != 'ascent'}, open('orbit3d.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('i=%.2f a=%.0f km period=%.1f min v=%.2f km/s' % (m['inc'], m['a'], m['period'] / 60, m['v_orb']))
    for ring, name in m['imp']:
        print(name, 'center', round(sum(p[0] for p in ring)/4, 3), round(sum(p[1] for p in ring)/4, 3))
    plot2(m)
