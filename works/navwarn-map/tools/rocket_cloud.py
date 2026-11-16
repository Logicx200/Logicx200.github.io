#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火箭云（暮光效应 / 夜光航迹）观测区预测

原理：
  发射时地面已进晨昏蒙影（太阳高度 < -6°），但火箭飞到的 50–150 km 高空仍被阳光照亮；
  地面观测者若同时满足
    (1) 天空足够暗：观测点太阳高度角 e_obs < -6°（更佳 < -12°）；
    (2) 尾迹被照亮：尾迹所在（星下点）太阳高度 e_plume > -β(h)，β=acos(R/(R+h)) 为高度 h 处的地平俯角；
    (3) 尾迹在地平线以上：观测点到尾迹星下点的大圆距离 < R·β(h)；
  就能看到火箭云。

输入：../trajectory3d.json（修正后的 3DOF 弹道，含上升段采样）
输出：../rocket_cloud.png（观测区预测图）；同时打印城市可见性表。

用法: python rocket_cloud.py
"""
import json
import math
import os
import datetime
import numpy as np

R = 6371.0088  # km
T0_ISO = '2026-11-18T22:44:30+00:00'
T0 = 1795041870.0
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 观测判据（太阳高度角，单位度）
DARK_VISIBLE = -6.0     # 民用晨昏蒙影结束：天空足够暗
DARK_BEST = -12.0       # 航海晨昏蒙影：对比度更好
PLUME_MIN_ALT = 40.0    # 尾迹高度下限（km）：再低就在地球阴影里了（随太阳高度变化）
PLUME_KEY_ALT = 80.0    # 主要“火箭云”段（km）


# ----------------------------------------------------------------- 太阳位置
def sun_position(ts):
    """返回 (太阳赤纬 deg, 星下点经度 deg, 太阳赤经 deg, GMST deg)。Meeus 低精度，误差 <0.01°。"""
    jd = 2440587.5 + ts / 86400.0
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T * T) % 360.0
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    ecc = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M) + 0.000289 * math.sin(3 * M))
    tl = L0 + C
    om = math.radians(125.04 - 1934.136 * T)
    al = math.radians(tl - 0.00569 - 0.00478 * math.sin(om))
    eps0 = 23.0 + (26.0 + ((21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60.0)) / 60.0
    eps = math.radians(eps0 + 0.00256 * math.cos(om))
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(al)))
    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(al), math.cos(al))) % 360.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * T * T - T ** 3 / 38710000.0) % 360.0
    lonsub = (ra - gmst + 180.0) % 360.0 - 180.0
    return dec, lonsub, ra, gmst


def sun_elev(lat, lon, dec, lonsub):
    """太阳高度角（deg），支持 numpy 广播。"""
    H = np.radians((lon - lonsub + 180.0) % 360.0 - 180.0)
    la = np.radians(lat)
    d = math.radians(dec)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(d) + np.cos(la) * np.cos(d) * np.cos(H)))


def horizon_dip(h_km):
    """高度 h 处的地平俯角 β（deg），也是可见大圆距离对应的地心角。"""
    return math.degrees(math.acos(R / (R + h_km)))


def hav_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def look_angles(obs_lat, obs_lon, p_lat, p_lon, h_km):
    """从地面观测点看高度 h 的尾迹的仰角、方位角、斜距。"""
    d = hav_km(obs_lat, obs_lon, p_lat, p_lon)
    th = d / R  # 地心角（rad），不要再 radians() 一次
    rp = R + h_km
    up = rp * math.cos(th) - R
    hor = rp * math.sin(th)
    elev = math.degrees(math.atan2(up, hor))
    slant = math.hypot(up, hor)
    az = bearing_deg(obs_lat, obs_lon, p_lat, p_lon)
    return elev, az, slant


# ----------------------------------------------------------------- 弹道与尾迹
def load_ascent():
    src = json.load(open(os.path.join(ROOT, 'trajectory3d.json'), encoding='utf-8'))
    samples = [s for s in src['samples'] if s[4] == 'ascent']
    # 去重/排序，补上二级一次关机点
    out = []
    for s in samples:
        out.append(dict(t=float(s[3]), lat=float(s[0]), lon=float(s[1]), alt=float(s[2])))
    ev = {e['ev']: e for e in src['events']}
    cut = ev.get('二级一次关机')
    if cut:
        out.append(dict(t=cut['t'], lat=cut['lat'], lon=cut['lon'], alt=cut['alt_km']))
    out.sort(key=lambda x: x['t'])
    return out, src


def plume_points(ascent):
    """挑选被阳光照亮的尾迹采样点。"""
    pts = []
    for p in ascent:
        if p['alt'] < PLUME_MIN_ALT:
            continue
        ts = T0 + p['t']
        dec, lonsub, _, _ = sun_position(ts)
        e_plume = float(sun_elev(p['lat'], p['lon'], dec, lonsub))
        beta = horizon_dip(p['alt'])
        if e_plume > -beta:
            pts.append(dict(p, sun_elev=e_plume, beta=beta, dmax=R * math.radians(beta)))
    return pts


# ----------------------------------------------------------------- 观测区网格
def observation_mask(plume, lon0=70.0, lon1=140.0, lat0=0.0, lat1=60.0, step=0.2):
    lons = np.arange(lon0, lon1 + 1e-9, step)
    lats = np.arange(lat0, lat1 + 1e-9, step)
    LON, LAT = np.meshgrid(lons, lats)
    vis = np.zeros(LAT.shape, dtype=bool)
    dark6 = np.zeros(LAT.shape, dtype=bool)   # 任一样本时刻满足 < -6
    best12 = np.zeros(LAT.shape, dtype=bool)
    # 按时间分组前的逐点并集：只要存在一个时刻同时满足即可，这里逐样本判断后 OR
    hit6 = np.zeros(LAT.shape, dtype=bool)
    hit12 = np.zeros(LAT.shape, dtype=bool)
    for p in plume:
        d = hav_km(LAT, LON, p['lat'], p['lon'])
        within = d <= p['dmax']
        ts = T0 + p['t']
        dec, lonsub, _, _ = sun_position(ts)
        e_obs = sun_elev(LAT, LON, dec, lonsub)
        hit6 |= within & (e_obs < DARK_VISIBLE)
        hit12 |= within & (e_obs < DARK_BEST)
    # 参考时刻的“天空足够暗”场（用于叠色/说明）
    return LON, LAT, hit6, hit12


# ----------------------------------------------------------------- 城市可见性
CITIES = [
    ('北京', 39.90, 116.40), ('太原', 38.85, 111.61), ('西安', 34.34, 108.94),
    ('兰州', 36.06, 103.83), ('银川', 38.49, 106.23), ('呼和浩特', 40.84, 111.75),
    ('成都', 30.57, 104.07), ('重庆', 29.56, 106.55), ('郑州', 34.75, 113.62),
    ('武汉', 30.59, 114.30), ('西宁', 36.62, 101.78), ('酒泉', 39.73, 98.49),
    ('敦煌', 40.14, 94.66), ('乌鲁木齐', 43.83, 87.62), ('上海', 31.23, 121.47),
    ('南京', 32.06, 118.80), ('石家庄', 38.04, 114.51), ('包头', 40.66, 109.84),
]


def city_report(plume):
    rows = []
    for name, la, lo in CITIES:
        best = None
        for p in plume:
            if p['alt'] < PLUME_KEY_ALT:
                continue
            el, az, slant = look_angles(la, lo, p['lat'], p['lon'], p['alt'])
            if el <= 0:
                continue
            ts = T0 + p['t']
            dec, lonsub, _, _ = sun_position(ts)
            e_obs = float(sun_elev(la, lo, dec, lonsub))
            if e_obs >= DARK_VISIBLE:
                continue
            if best is None or el > best[0]:
                best = (el, p, e_obs, az, slant)
        if best:
            el, p, e_obs, az, slant = best
            rows.append(dict(name=name, lat=la, lon=lo, t=p['t'], alt=p['alt'],
                             plume_lat=p['lat'], plume_lon=p['lon'],
                             elev=el, az=az, slant=slant, sun=e_obs,
                             best=(e_obs < DARK_BEST)))
    return rows


def cst_clock(t_s):
    base = datetime.datetime(2026, 11, 19, 6, 44, 30)
    d = base + datetime.timedelta(seconds=float(t_s))
    return d.strftime('%H:%M:%S')


# ----------------------------------------------------------------- 作图
def plot(LON, LAT, vis6, vis12, plume, ascent, cities, out_png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    import matplotlib.ticker as mticker
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import gaussian_filter

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    BG_OCEAN = '#07131c'
    BG_LAND = '#14313f'
    COAST = '#3c7f9e'
    BORDER = '#215066'

    fig = plt.figure(figsize=(13.6, 10.2), facecolor=BG_OCEAN)
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree(), facecolor=BG_OCEAN)
    ax.set_extent([80, 136, 8, 56], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale('50m'), facecolor=BG_OCEAN, zorder=0)
    ax.add_feature(cfeature.LAND.with_scale('50m'), facecolor=BG_LAND, zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale('50m'), facecolor=BG_OCEAN, edgecolor=COAST, linewidth=.3, zorder=0)
    ax.add_feature(cfeature.BORDERS.with_scale('50m'), edgecolor=BORDER, linewidth=.7, zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale('50m'), edgecolor=COAST, linewidth=.7, zorder=1)
    gl = ax.gridlines(draw_labels=True, linewidth=.4, color='#16394a', alpha=.7,
                      xlocs=mticker.MultipleLocator(10), ylocs=mticker.MultipleLocator(10))
    gl.top_labels = False; gl.right_labels = False
    gl.xlabel_style = dict(color='#6f8794', fontsize=8)
    gl.ylabel_style = dict(color='#6f8794', fontsize=8)

    # ---- 观测区（平滑后填色）----
    s6 = gaussian_filter(vis6.astype(float), 2.0)
    s12 = gaussian_filter(vis12.astype(float), 2.0)
    ax.contourf(LON, LAT, s6, levels=[0.35, 1.1], colors=['#ffb74d'], alpha=0.20,
                transform=ccrs.PlateCarree(), zorder=3)
    ax.contourf(LON, LAT, s12, levels=[0.35, 1.1], colors=['#ff7043'], alpha=0.40,
                transform=ccrs.PlateCarree(), zorder=3)
    # 边界线
    ax.contour(LON, LAT, s6, levels=[0.5], colors=['#ffb74d'], linewidths=1.4,
               transform=ccrs.PlateCarree(), zorder=4)
    ax.contour(LON, LAT, s12, levels=[0.5], colors=['#ff7043'], linewidths=1.4,
               transform=ccrs.PlateCarree(), zorder=4)

    # ---- 晨昏线（参考时刻：尾迹中段 06:48:50 CST）----
    t_ref = 250.0
    dec, lonsub, _, _ = sun_position(T0 + t_ref)
    egrid = sun_elev(LAT, LON, dec, lonsub)
    cs = ax.contour(LON, LAT, egrid, levels=[-18, -12, -6, 0],
                    colors=['#4dd0e1', '#29b6f6', '#80deea', '#eceff1'],
                    linewidths=[0.9, 1.1, 1.4, 1.6], linestyles='--',
                    transform=ccrs.PlateCarree(), zorder=5)
    ax.clabel(cs, fmt=lambda v: f'{v:g}°', fontsize=8, colors='#b0bec5', inline=True)

    # ---- 弹道地面轨迹 ----
    la = [p['lat'] for p in ascent]
    lo = [p['lon'] for p in ascent]
    ax.plot(lo, la, color='#ffd54f', linewidth=2.4, transform=ccrs.PlateCarree(), zorder=7)
    # 被照亮的尾迹段（按样本）
    if plume:
        ax.scatter([p['lon'] for p in plume], [p['lat'] for p in plume],
                   c=[p['alt'] for p in plume], cmap='autumn', s=16, zorder=8,
                   transform=ccrs.PlateCarree(), edgecolors='none')
    # 发射场
    ax.plot(111.608, 38.849, marker='^', markersize=11, color='#4dd0e1',
            markeredgecolor='#04121a', zorder=9, transform=ccrs.PlateCarree())
    ax.text(112.15, 39.55, '太原', color='#4dd0e1', fontsize=10,
            transform=ccrs.PlateCarree(), zorder=10)
    # 尾迹关键时刻
    for tt, lab in [(200, '06:47:50'), (250, '06:48:40'), (310, '06:49:40')]:
        cand = min(plume, key=lambda p: abs(p['t'] - tt)) if plume else None
        if cand:
            ax.plot(cand['lon'], cand['lat'], marker='o', markersize=5, color='#ff5252',
                    markeredgecolor='#ffd54f', zorder=9, transform=ccrs.PlateCarree())
            ax.text(cand['lon'] + 0.6, cand['lat'] - 1.6, f"{lab} · {cand['alt']:.0f} km",
                    color='#ffd54f', fontsize=8, transform=ccrs.PlateCarree(), zorder=10)

    # ---- 城市 ----
    vis_names = {c['name'] for c in cities}
    label_cities = {'酒泉', '兰州', '银川', '西安', '成都', '重庆', '呼和浩特'}
    offs = {'酒泉': (0.6, 0.8), '兰州': (0.7, 0.5), '银川': (0.6, 0.9),
            '西安': (0.6, -1.4), '成都': (0.6, -1.3), '重庆': (0.6, -1.3),
            '呼和浩特': (0.6, 0.9)}
    for name, la_, lo_ in CITIES:
        ok = name in vis_names
        ax.plot(lo_, la_, marker='o', markersize=4.6 if ok else 2.8,
                color='#7cf2c0' if ok else '#607d8b',
                markeredgecolor='#04121a', zorder=11, transform=ccrs.PlateCarree())
        if ok and name in label_cities:
            dx, dy = offs.get(name, (0.6, 0.7))
            ax.text(lo_ + dx, la_ + dy, name, color='#cfe0e8', fontsize=8.4,
                    transform=ccrs.PlateCarree(), zorder=12)

    # ---- 标题/说明 ----
    fig.suptitle('火箭云（暮光效应）观测区预测 · 太原发射 2026-11-19 06:44:30 CST（22:44:30 UTC）',
                 color='#e8f5fb', fontsize=16, y=0.975)
    ax.set_title('尾迹 50–150 km 被阳光照亮 ＋ 地面太阳高度 < -6° ＋ 尾迹高于地平线 → 可观测'
                 '（< -12° 区域对比度更佳）',
                 color='#9fc6da', fontsize=10.5, pad=8)

    legend_items = [
        Patch(facecolor='#ffb74d', alpha=.35, edgecolor='#ffb74d', label='可见区（太阳高度 < -6°）'),
        Patch(facecolor='#ff7043', alpha=.55, edgecolor='#ff7043', label='最佳观测区（< -12°）'),
        Line2D([0], [0], color='#ffd54f', lw=2.4, label='上升段地面轨迹（修正后弹道）'),
        Line2D([0], [0], color='#4dd0e1', lw=1.0, ls='--', label='晨昏线（-18°）'),
        Line2D([0], [0], color='#29b6f6', lw=1.2, ls='--', label='晨昏线（-12°）'),
        Line2D([0], [0], color='#80deea', lw=1.4, ls='--', label='晨昏线（-6°）'),
        Line2D([0], [0], color='#eceff1', lw=1.5, ls='--', label='晨昏线（0° 日出）'),
        Line2D([0], [0], marker='o', color='#ff5252', lw=0, label='尾迹样本（06:47–06:50）'),
        Line2D([0], [0], marker='o', color='#7cf2c0', lw=0, label='可见城市'),
    ]
    ax.legend(handles=legend_items, loc='lower left', facecolor='#0d2532',
              edgecolor='#4dd0e1', labelcolor='#dff3fb', fontsize=8.2, framealpha=.94)

    cell = (0.2 * 111.32 * np.cos(np.radians(LAT))) * (0.2 * 110.57)
    a6 = (vis6 * cell).sum() / 1e4
    a12 = (vis12 * cell).sum() / 1e4
    info = ['T0 = 06:44:30 CST（清晨发射）',
            '发射点太阳高度 ≈ -7.3°（民用晨昏蒙影）',
            '尾迹照亮段 06:46:50–06:49:40 CST · 47–152 km',
            '可见地平距离 1130–1380 km（尾迹 100–150 km）',
            f'可见区 ≈ {a6:.0f} 万 km² · 最佳区 ≈ {a12:.0f} 万 km²',
            '核心区：甘、宁、陕、川、渝、青东、内蒙中西部']
    ax.text(0.985, 0.975, '\n'.join(info), transform=ax.transAxes, ha='right', va='top',
            color='#9fc6da', fontsize=8.0, family='Microsoft YaHei', zorder=20,
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#0d2532', edgecolor='#2c6b8a', alpha=.92))

    # 城市表
    lines = ['观测城市    仰角   方位  太阳高度']
    for c in sorted(cities, key=lambda x: -x['elev'])[:10]:
        lines.append(f"{c['name']:<6}{c['elev']:6.1f}° {c['az']:5.0f}° {c['sun']:7.1f}°")
    ax.text(0.985, 0.02, '\n'.join(lines), transform=ax.transAxes, ha='right', va='bottom',
            color='#cfe0e8', fontsize=7.8, family='Microsoft YaHei', zorder=20,
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#0d2532', edgecolor='#2c6b8a', alpha=.92))

    fig.text(0.5, 0.012, '预测模型：修正后 3DOF 弹道 + Meeus 太阳位置；假设晴空、无地形遮挡；实际可见性受天气/尾迹扩散影响。',
             ha='center', color='#6f8794', fontsize=8)
    fig.subplots_adjust(left=0.045, right=0.985, top=0.925, bottom=0.055)
    fig.savefig(out_png, dpi=170, facecolor=fig.get_facecolor())
    print('saved', out_png)


def export_js(LON, LAT, vis6, vis12, plume, cities, out_js):
    """导出网页图层数据 ../rocketcloud.js（供 index.html 的 Leaflet 图层使用）。"""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from scipy.ndimage import gaussian_filter

    s6 = gaussian_filter(vis6.astype(float), 2.0)
    s12 = gaussian_filter(vis12.astype(float), 2.0)
    t_ref = 250.0
    dec, lonsub, _, _ = sun_position(T0 + t_ref)
    egrid = sun_elev(LAT, LON, dec, lonsub)

    fig = Figure()
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    cs6 = ax.contour(LON, LAT, s6, levels=[0.5])
    cs12 = ax.contour(LON, LAT, s12, levels=[0.5])
    ct = ax.contour(LON, LAT, egrid, levels=[-18, -12, -6, 0])

    def rings(cs):
        out = []
        for seg in cs.allsegs[0]:
            if len(seg) >= 4:
                r = [[round(float(y), 3), round(float(x), 3)] for x, y in seg]
                if r[0] != r[-1]:
                    r.append(r[0])
                out.append(r)
        return out

    def lines(cs, level):
        out = []
        for seg in cs.allsegs[list(cs.levels).index(level)]:
            if len(seg) >= 2:
                out.append([[round(float(y), 3), round(float(x), 3)] for x, y in seg])
        return out

    vis_polys = rings(cs6)
    best_polys = rings(cs12)
    terminators = []
    for lev in (-18, -12, -6, 0):
        for seg in lines(ct, lev):
            terminators.append(dict(level=lev, pts=seg))

    vis_map = {c['name']: c for c in cities}
    dec0, lonsub0, _, _ = sun_position(T0 + t_ref)
    cities_out = []
    for name, la, lo in CITIES:
        c = vis_map.get(name)
        sun = round(float(sun_elev(la, lo, dec0, lonsub0)), 1)
        cities_out.append(dict(name=name, lat=round(la, 3), lon=round(lo, 3),
                               visible=bool(c),
                               elev=round(c['elev'], 1) if c else None,
                               az=round(c['az']) if c else None, sun=sun))

    cell = (0.2 * 111.32 * np.cos(np.radians(LAT))) * (0.2 * 110.57)
    a6 = (vis6 * cell).sum() / 1e4
    a12 = (vis12 * cell).sum() / 1e4
    data = dict(
        t0_utc=T0_ISO, t0_cst='2026-11-19 06:44:30',
        summary=(f'尾迹被照亮 06:46:50–06:49:40 CST；可见区约 {a6:.0f} 万 km²，'
                 f'最佳区约 {a12:.0f} 万 km²'),
        note='理论预测：假设晴空、无地形遮挡；未模拟尾迹扩散/亮度；-6°/-12° 为晨昏蒙影经验阈值。',
        visible=vis_polys, best=best_polys, terminators=terminators, cities=cities_out,
        plume=[dict(t=round(p['t'], 1), lat=round(p['lat'], 3), lon=round(p['lon'], 3),
                    alt=round(p['alt'], 1)) for p in plume],
    )
    with open(out_js, 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：rocket_cloud.py —— 火箭云观测区预测（供 index.html 图层使用） */\n')
        f.write('window.ROCKET_CLOUD = ')
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print('wrote', out_js, '| visible rings', len(vis_polys), '| best rings', len(best_polys),
          '| terminator segs', len(terminators), '| cities', len(cities_out))


# ----------------------------------------------------------------- 连续观测质量 Q
def ecef_grid(lat, lon, r):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([r * np.cos(la) * np.cos(lo),
                     r * np.cos(la) * np.sin(lo),
                     r * np.sin(la)], axis=-1)


def quality_field(LAT, LON, plume, dark_center=-6.0, dark_w=2.2):
    """连续观测质量 Q ∈ [0,1]（相对值，未标定）。

    Q = D × L × V × C
      D: 天空暗度，logistic(e_obs, 中心 -6°, 宽度 2.2°) —— 晨昏线附近平滑过渡，右侧也有非零值
      L: 尾迹照亮余量，logistic(e_plume + β(h))
      V: 尾迹仰角，1-exp(-elev/4)（贴地平线→0，20°以上≈1）
      C: 与太阳的夹角，logistic(sep, 中心 35°, 宽度 12°)（正对晨光→小，背向太阳→大）
    对每个尾迹采样取 max（观测窗口内最好时刻）。"""
    Q = np.zeros(LAT.shape)
    obs = ecef_grid(LAT, LON, R)
    for p in plume:
        ts = T0 + p['t']
        dec, lonsub, _, _ = sun_position(ts)
        ep = float(sun_elev(p['lat'], p['lon'], dec, lonsub))
        beta = horizon_dip(p['alt'])
        m = ep + beta
        Lf = 1.0 / (1.0 + math.exp(-(m - 0.3) / 1.2))
        d = hav_km(LAT, LON, p['lat'], p['lon'])
        rp = R + p['alt']
        th = d / R
        elev = np.degrees(np.arctan2(rp * np.cos(th) - R, rp * np.sin(th)))
        Vf = 1.0 - np.exp(-np.maximum(elev, 0.0) / 4.0)
        pl = ecef_grid(np.array([p['lat']]), np.array([p['lon']]), R + p['alt'])[0]
        v = pl[None, None, :] - obs
        v = v / np.linalg.norm(v, axis=-1, keepdims=True)
        sun = np.array([math.cos(math.radians(dec)) * math.cos(math.radians(lonsub)),
                        math.cos(math.radians(dec)) * math.sin(math.radians(lonsub)),
                        math.sin(math.radians(dec))])
        sep = np.degrees(np.arccos(np.clip(np.sum(v * sun, axis=-1), -1, 1)))
        Cf = 1.0 / (1.0 + np.exp(-(sep - 35.0) / 12.0))
        e_obs = sun_elev(LAT, LON, dec, lonsub)
        Df = 1.0 / (1.0 + np.exp((e_obs - dark_center) / dark_w))
        q = Df * Lf * Vf * Cf
        q = np.where((elev > 0) & (m > -0.5), q, 0.0)
        Q = np.maximum(Q, q)
    return Q


# 质量色标（RGBA 停靠点）：透明深蓝 -> 青 -> 黄 -> 橙 -> 红
Q_STOPS = [(0.00, (13, 27, 42, 0.00)),
           (0.12, (38, 198, 218, 0.16)),
           (0.30, (255, 213, 79, 0.40)),
           (0.50, (255, 152, 0, 0.60)),
           (0.72, (244, 81, 30, 0.78)),
           (1.00, (198, 40, 40, 0.90))]


def _q_rgb(q):
    q = np.clip(q, 0, 1)
    out = np.zeros(q.shape + (4,))
    for i in range(len(Q_STOPS) - 1):
        q0, c0 = Q_STOPS[i]
        q1, c1 = Q_STOPS[i + 1]
        m = (q >= q0) & (q <= q1)
        f = np.zeros_like(q)
        f[m] = (q[m] - q0) / (q1 - q0)
        for k in range(3):
            out[..., k] = np.where(m, c0[k] / 255.0 + (c1[k] - c0[k]) / 255.0 * f, out[..., k])
        # alpha 已经是 0–1，不再除 255
        out[..., 3] = np.where(m, c0[3] + (c1[3] - c0[3]) * f, out[..., 3])
    return out


def _q_cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(
        'rcloud_q', [(s[0], (s[1][0] / 255, s[1][1] / 255, s[1][2] / 255, s[1][3])) for s in Q_STOPS])


def compute_quality(step=0.1, lon0=76, lon1=130, lat0=10, lat1=58):
    lons = np.arange(lon0, lon1 + 1e-9, step)
    lats = np.arange(lat0, lat1 + 1e-9, step)
    LON, LAT = np.meshgrid(lons, lats)
    ascent, src = load_ascent()
    plume = plume_points(ascent)
    Q = quality_field(LAT, LON, plume)
    qmax = float(Q.max()) if Q.max() > 0 else 1.0
    return LON, LAT, Q / qmax, plume, ascent, (lon0, lon1, lat0, lat1)


def _city_q(Q, LON, LAT, cities):
    import scipy.interpolate as si
    lons = LON[0, :]; lats = LAT[:, 0]
    f = si.RegularGridInterpolator((lats, lons), Q, bounds_error=False, fill_value=0.0)
    out = []
    for c in cities:
        q = float(f((c['lat'], c['lon'])))
        out.append(dict(name=c['name'], lat=c['lat'], lon=c['lon'], q=round(q, 3),
                        elev=c.get('elev'), az=c.get('az'), sun=c.get('sun')))
    return out


def plot_quality(LON, LAT, Q, plume, ascent, out_png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.patches import Patch
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from scipy.ndimage import gaussian_filter

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    BG = '#07131c'
    fig = plt.figure(figsize=(14.2, 10.4), facecolor=BG)
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree(), facecolor=BG)
    ax.set_extent([80, 128, 14, 55], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale('50m'), facecolor=BG, zorder=0)
    ax.add_feature(cfeature.LAND.with_scale('50m'), facecolor='#14313f', zorder=0)
    ax.add_feature(cfeature.BORDERS.with_scale('50m'), edgecolor='#215066', linewidth=.7, zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale('50m'), edgecolor='#3c7f9e', linewidth=.7, zorder=1)
    gl = ax.gridlines(draw_labels=True, linewidth=.4, color='#16394a', alpha=.7,
                      xlocs=mticker.MultipleLocator(10), ylocs=mticker.MultipleLocator(10))
    gl.top_labels = False; gl.right_labels = False
    gl.xlabel_style = dict(color='#6f8794', fontsize=8)
    gl.ylabel_style = dict(color='#6f8794', fontsize=8)

    Qs = gaussian_filter(Q, 1.2)
    pcm = ax.pcolormesh(LON, LAT, Qs, cmap=_q_cmap(), vmin=0, vmax=1, shading='auto',
                        transform=ccrs.PlateCarree(), zorder=3)
    ax.contour(LON, LAT, Qs, levels=[0.2, 0.4, 0.6], colors=['#b3e5fc', '#ffe082', '#ff8a65'],
               linewidths=[0.8, 1.0, 1.2], transform=ccrs.PlateCarree(), zorder=4)
    cbar = fig.colorbar(pcm, ax=ax, orientation='vertical', fraction=0.026, pad=0.012, shrink=0.62)
    cbar.set_label('相对观测质量 Q（最高点=1，未标定）', color='#9fc6da', fontsize=9)
    cbar.ax.tick_params(colors='#6f8794', labelsize=8)
    cbar.outline.set_edgecolor('#2c6b8a')

    # 晨昏线（参考时刻 06:48:40 CST）
    t_ref = 250.0
    dec, lonsub, _, _ = sun_position(T0 + t_ref)
    egrid = sun_elev(LAT, LON, dec, lonsub)
    cs = ax.contour(LON, LAT, egrid, levels=[-18, -12, -6, 0],
                    colors=['#4dd0e1', '#29b6f6', '#80deea', '#eceff1'],
                    linewidths=[0.9, 1.1, 1.4, 1.6], linestyles='--',
                    transform=ccrs.PlateCarree(), zorder=5)
    ax.clabel(cs, fmt=lambda v: f'{v:g}°', fontsize=8, colors='#b0bec5', inline=True)

    # 轨迹 + 尾迹关键时刻
    la = [p['lat'] for p in ascent]; lo = [p['lon'] for p in ascent]
    ax.plot(lo, la, color='#ffd54f', linewidth=2.2, transform=ccrs.PlateCarree(), zorder=7)
    ax.plot(111.608, 38.849, marker='^', markersize=10, color='#4dd0e1',
            markeredgecolor='#04121a', zorder=9, transform=ccrs.PlateCarree())
    ax.text(112.3, 37.9, '太原', color='#4dd0e1', fontsize=10, transform=ccrs.PlateCarree(), zorder=10)
    for tt, lab in [(200, '06:47:50'), (250, '06:48:40'), (310, '06:49:40')]:
        cand = min(plume, key=lambda p: abs(p['t'] - tt))
        ax.plot(cand['lon'], cand['lat'], marker='o', markersize=5, color='#ff5252',
                markeredgecolor='#ffd54f', zorder=9, transform=ccrs.PlateCarree())
        ax.text(cand['lon'] + 0.6, cand['lat'] - 1.6, f"{lab} · {cand['alt']:.0f} km",
                color='#ffd54f', fontsize=8, transform=ccrs.PlateCarree(), zorder=10)

    # 城市：按 Q 着色/标注
    cq = _city_q(Q, LON, LAT, [dict(name=n, lat=la_, lon=lo_) for n, la_, lo_ in CITIES])
    label_set = {'西安', '银川', '兰州', '成都', '重庆', '呼和浩特', '包头'}
    for c in cq:
        col = '#ffffff' if c['q'] > 0.55 else ('#ffd54f' if c['q'] > 0.3 else '#90a4ae')
        ax.plot(c['lon'], c['lat'], marker='o', markersize=4.5 if c['q'] > 0.3 else 3,
                color=col, markeredgecolor='#04121a', zorder=11, transform=ccrs.PlateCarree())
        if c['name'] in label_set:
            dx, dy = {'包头': (0.6, -2.0), '呼和浩特': (0.6, 0.8), '银川': (0.6, 0.8),
                      '兰州': (0.6, -1.6), '西安': (0.6, -1.6), '成都': (0.6, -1.6),
                      '重庆': (0.6, -1.6)}.get(c['name'], (0.6, 0.7))
            ax.text(c['lon'] + dx, c['lat'] + dy, f"{c['name']} {c['q']*100:.0f}%",
                    color='#cfe0e8', fontsize=8.2, transform=ccrs.PlateCarree(), zorder=12)

    fig.suptitle('火箭云观测质量 Q(lat,lon) · 太原发射 2026-11-19 06:44:30 CST',
                 color='#e8f5fb', fontsize=16, y=0.965)
    ax.set_title('连续质量场：晨昏线（-6°/-12°）附近平滑过渡，线右侧/贴线处 Q>0；高 Q 区偏北（背向太阳、仰角适中）',
                 color='#9fc6da', fontsize=10, pad=6)

    # 35°N 剖面：直接展示“晨昏线右侧非零”
    axin = fig.add_axes([0.655, 0.150, 0.300, 0.190], facecolor='#0d2532')
    row = int(np.argmin(np.abs(LAT[:, 0] - 35.0)))
    lons = LON[0, :]
    axin.fill_between(lons, 0, Q[row, :], color='#ff7043', alpha=.55)
    axin.plot(lons, Q[row, :], color='#ffd54f', lw=1.2)
    for lev, col in ((-6, '#80deea'), (0, '#eceff1')):
        # 找 35N 上该太阳高度的经度（晨侧）
        eg = sun_elev(35.0, lons, dec, lonsub)
        idx = np.where(np.diff(np.sign(eg - lev)) != 0)[0]
        for ii in idx:
            lo_x = lons[ii]
            if 95 <= lo_x <= 128:
                axin.axvline(lo_x, color=col, ls='--', lw=1.1)
                axin.text(lo_x + 0.4, 0.92, f'{lev}°', color=col, fontsize=7.5)
    axin.set_xlim(95, 128); axin.set_ylim(0, 1.0)
    axin.set_xlabel('经度 / °E（35°N 剖面）', color='#9fc6da', fontsize=7.5)
    axin.set_ylabel('Q', color='#9fc6da', fontsize=7.5)
    axin.tick_params(colors='#6f8794', labelsize=7)
    for s in axin.spines.values(): s.set_color('#2c6b8a')
    axin.set_title('35°N：跨晨昏线的平滑衰减（右侧仍非零）', color='#cfe0e8', fontsize=8, pad=3)

    info = ['T0 06:44:30 CST · 发射点太阳高度 -7.25°',
            'Q 由 4 个因子相乘：天空暗度 / 尾迹照亮 / 仰角 / 背向太阳',
            '质量最高点在包头—西安—重庆一带（Q≈90-100%）',
            '酒泉 Q≈8%（贴地平线 + 正对晨光）；兰州 Q≈47%（正对晨光）',
            '比例未标定：只表示相对观测条件好坏']
    ax.text(0.015, 0.02, '\n'.join(info), transform=ax.transAxes, ha='left', va='bottom',
            color='#9fc6da', fontsize=8.0, zorder=20,
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#0d2532', edgecolor='#2c6b8a', alpha=.92))
    fig.text(0.5, 0.012, '模型：修正后 3DOF 弹道 + Meeus 太阳位置；未模拟尾迹亮度/扩散/天气；Q 为相对质量，不是统计概率。',
             ha='center', color='#6f8794', fontsize=8)
    fig.subplots_adjust(left=0.045, right=0.985, top=0.925, bottom=0.055)
    fig.savefig(out_png, dpi=170, facecolor=fig.get_facecolor())
    print('saved', out_png)


def export_web_quality(LON, LAT, Q, plume, out_png, out_js):
    """网页用：Mercator 透明热力图 PNG + rocketcloud.js（质量场版本）。"""
    from PIL import Image
    import scipy.interpolate as si

    lon0, lon1 = float(LON[0, 0]), float(LON[0, -1])
    lat0, lat1 = float(LAT[0, 0]), float(LAT[-1, 0])
    f = si.RegularGridInterpolator((LAT[:, 0], LON[0, :]), Q, bounds_error=False, fill_value=0.0)

    W, H = 1100, 820
    lons = np.linspace(lon0, lon1, W)
    y0 = math.log(math.tan(math.pi / 4 + math.radians(lat0) / 2))
    y1 = math.log(math.tan(math.pi / 4 + math.radians(lat1) / 2))
    ys = np.linspace(y0, y1, H)
    lats = np.degrees(2 * np.arctan(np.exp(ys)) - math.pi / 2)
    LONP, LATP = np.meshgrid(lons, lats)
    QP = f(np.stack([LATP.ravel(), LONP.ravel()], axis=-1)).reshape(LATP.shape)
    rgba = _q_rgb(QP)
    # 低值完全透明，高值更实
    rgba[..., 3] = np.where(QP < 0.015, 0.0, rgba[..., 3] * np.clip(0.35 + QP, 0, 1))
    Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), 'RGBA').save(out_png)
    print('saved', out_png)

    cities = _city_q(Q, LON, LAT, [dict(name=n, lat=la, lon=lo) for n, la, lo in CITIES])
    dec0, lonsub0, _, _ = sun_position(T0 + 250.0)
    for c in cities:
        c['sun'] = round(float(sun_elev(c['lat'], c['lon'], dec0, lonsub0)), 1)
        best = None
        for p in plume:
            el, az, _ = look_angles(c['lat'], c['lon'], p['lat'], p['lon'], p['alt'])
            if best is None or el > best[0]:
                best = (el, az)
        c['elev'] = round(best[0], 1) if best else None
        c['az'] = round(best[1]) if best else None
        c['visible'] = bool(c['elev'] is not None and c['elev'] > 0)

    t_ref = 250.0
    dec, lonsub, _, _ = sun_position(T0 + t_ref)
    egrid = sun_elev(LAT, LON, dec, lonsub)
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(); FigureCanvasAgg(fig); ax = fig.add_subplot(111)
    ct = ax.contour(LON, LAT, egrid, levels=[-18, -12, -6, 0])
    terminators = []
    for li, lev in enumerate([-18, -12, -6, 0]):
        for seg in ct.allsegs[li]:
            if len(seg) >= 2:
                terminators.append(dict(level=lev, pts=[[round(float(y), 3), round(float(x), 3)] for x, y in seg]))

    data = dict(
        t0_utc=T0_ISO, t0_cst='2026-11-19 06:44:30',
        summary='连续观测质量场（Q 0–1，最高点归一为 1）；晨昏线右侧贴线处仍有非零概率',
        note='Q = 天空暗度 × 尾迹照亮 × 仰角 × 背向太阳；相对质量，不是统计概率；未模拟尾迹亮度/扩散/天气。',
        quality=dict(image=os.path.basename(out_png),
                     bounds=[[round(lat0, 3), round(lon0, 3)], [round(lat1, 3), round(lon1, 3)]],
                     stops=[[s[0], '#%02x%02x%02x' % s[1][:3], s[1][3]] for s in Q_STOPS]),
        terminators=terminators,
        cities=cities,
        plume=[dict(t=round(p['t'], 1), lat=round(p['lat'], 3), lon=round(p['lon'], 3),
                    alt=round(p['alt'], 1)) for p in plume],
    )
    iy, ix = np.unravel_index(int(np.argmax(Q)), Q.shape)
    data['q_peak'] = dict(lat=round(float(LAT[iy, ix]), 3), lon=round(float(LON[iy, ix]), 3),
                          q=round(float(Q[iy, ix]), 3))
    cell = (0.1 * 111.32 * np.cos(np.radians(LAT))) * (0.1 * 110.57)
    data['q_stats'] = dict(gt03=round(float(((Q > 0.3) * cell).sum()) / 1e4, 1),
                           gt06=round(float(((Q > 0.6) * cell).sum()) / 1e4, 1))
    with open(out_js, 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：rocket_cloud.py —— 火箭云观测质量场（网页图层） */\n')
        f.write('window.ROCKET_CLOUD = ')
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print('wrote', out_js, '| cities', len(cities), '| terminators', len(terminators))


def main():
    ascent, src = load_ascent()
    plume = plume_points(ascent)
    print('ascent samples', len(ascent), '| sunlit plume samples', len(plume),
          '| time %.0f..%.0f s | alt %.0f..%.0f km' % (
              plume[0]['t'], plume[-1]['t'], plume[0]['alt'], plume[-1]['alt']) if plume else '')
    dec, lonsub, _, _ = sun_position(T0)
    print('T0 sun: dec=%.3f  subsolar lon=%.3f' % (dec, lonsub))
    print('sun elev Taiyuan %.2f, Xi\'an %.2f, Lanzhou %.2f, Beijing %.2f' % (
        float(sun_elev(38.849, 111.608, dec, lonsub)),
        float(sun_elev(34.34, 108.94, dec, lonsub)),
        float(sun_elev(36.06, 103.83, dec, lonsub)),
        float(sun_elev(39.90, 116.40, dec, lonsub))))
    LON, LAT, vis6, vis12 = observation_mask(plume)
    cell_km2 = (0.2 * 111.32 * np.cos(np.radians(LAT))) * (0.2 * 110.57)
    print('visible area: %.1f x1e4 km2 | best %.1f x1e4 km2' % (
        (vis6 * cell_km2).sum() / 1e4, (vis12 * cell_km2).sum() / 1e4))
    if vis6.any():
        iy, ix = np.where(vis6)
        print('visible bbox lat %.1f..%.1f lon %.1f..%.1f' % (
            LAT[iy, ix].min(), LAT[iy, ix].max(), LON[iy, ix].min(), LON[iy, ix].max()))
    cities = city_report(plume)
    print('\ncity visibility:')
    for c in sorted(cities, key=lambda x: -x['elev']):
        print('  %-5s elev %5.1f az %5.0f sun %6.1f  plume(t=%.0fs alt=%.0fkm)  best=%s' % (
            c['name'], c['elev'], c['az'], c['sun'], c['t'], c['alt'], c['best']))
    plot(LON, LAT, vis6, vis12, plume, ascent, cities, os.path.join(ROOT, 'rocket_cloud.png'))
    export_js(LON, LAT, vis6, vis12, plume, cities, os.path.join(ROOT, 'rocketcloud.js'))
    # 连续观测质量场
    LONq, LATq, Qn, plume_q, ascent_q, bounds = compute_quality()
    plot_quality(LONq, LATq, Qn, plume_q, ascent_q, os.path.join(ROOT, 'rocket_cloud_quality.png'))
    export_web_quality(LONq, LATq, Qn, plume,
                       os.path.join(ROOT, 'rocketcloud_quality.png'),
                       os.path.join(ROOT, 'rocketcloud.js'))


if __name__ == '__main__':
    main()



