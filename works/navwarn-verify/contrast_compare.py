# -*- coding: utf-8 -*-
"""Two-panel comparison: quality with the sun-contrast term vs without it."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
R = rc.R
lons = np.arange(100, 116 + 1e-9, 0.2)
lats = np.arange(28, 44 + 1e-9, 0.2)
LON, LAT = np.meshgrid(lons, lats)
la, lo = np.radians(LAT), np.radians(LON)
obs = np.stack([R*np.cos(la)*np.cos(lo), R*np.cos(la)*np.sin(lo), R*np.sin(la)], axis=-1)

Qc = np.zeros(LAT.shape)
Qn = np.zeros(LAT.shape)
for p in plume:
    ts = rc.T0 + p['t']
    dec, lonsub, _, _ = rc.sun_position(ts)
    ep = float(rc.sun_elev(p['lat'], p['lon'], dec, lonsub))
    beta = rc.horizon_dip(p['alt'])
    m = ep + beta
    L = 1/(1+math.exp(-(m-0.3)/1.2))
    d = rc.hav_km(LAT, LON, p['lat'], p['lon'])
    rp = R + p['alt']
    th = d/R
    elev = np.degrees(np.arctan2(rp*np.cos(th)-R, rp*np.sin(th)))
    V = 1-np.exp(-np.maximum(elev, 0)/4)
    la2, lo2 = np.radians(p['lat']), np.radians(p['lon'])
    pl = np.array([rp*math.cos(la2)*math.cos(lo2), rp*math.cos(la2)*math.sin(lo2), rp*math.sin(la2)])
    v = pl[None, None, :]-obs
    v = v/np.linalg.norm(v, axis=-1, keepdims=True)
    sun = np.array([math.cos(math.radians(dec))*math.cos(math.radians(lonsub)),
                    math.cos(math.radians(dec))*math.sin(math.radians(lonsub)),
                    math.sin(math.radians(dec))])
    sep = np.degrees(np.arccos(np.clip(np.sum(v*sun, axis=-1), -1, 1)))
    C = 1/(1+np.exp(-(sep-35)/12))
    e_obs = rc.sun_elev(LAT, LON, dec, lonsub)
    D = 1/(1+np.exp((e_obs+6)/2.2))
    ok = (elev > 0) & (m > -0.5)
    Qc = np.maximum(Qc, np.where(ok, D*L*V*C, 0))
    Qn = np.maximum(Qn, np.where(ok, D*L*V, 0))
Qc /= Qc.max(); Qn /= Qn.max()

cmap = rc._q_cmap()
fig = plt.figure(figsize=(13.6, 6.4), facecolor='#07131c')
for k, (Q, title) in enumerate([(Qc, '含“背向太阳”对比度项 → 两坨'),
                                (Qn, '去掉对比度项 → 单脊（最大值在 36°N,105°E）')]):
    ax = fig.add_subplot(1, 2, k+1, projection=ccrs.PlateCarree(), facecolor='#07131c')
    ax.set_extent([100, 116, 28, 44], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale('50m'), facecolor='#07131c', zorder=0)
    ax.add_feature(cfeature.LAND.with_scale('50m'), facecolor='#14313f', zorder=0)
    ax.add_feature(cfeature.BORDERS.with_scale('50m'), edgecolor='#215066', linewidth=.6, zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale('50m'), edgecolor='#3c7f9e', linewidth=.6, zorder=1)
    ax.pcolormesh(LON, LAT, Q, cmap=cmap, vmin=0, vmax=1, shading='auto',
                  transform=ccrs.PlateCarree(), zorder=3)
    ax.contour(LON, LAT, Q, levels=[0.4, 0.6, 0.8], colors='#b3e5fc', linewidths=.6,
               transform=ccrs.PlateCarree(), zorder=4)
    for name, la_, lo_ in rc.CITIES:
        if 100 <= lo_ <= 116 and 28 <= la_ <= 44:
            ax.plot(lo_, la_, 'o', ms=3, color='#fff', markeredgecolor='#04121a',
                    transform=ccrs.PlateCarree(), zorder=6)
            ax.text(lo_ + .25, la_ + .25, name, color='#cfe0e8', fontsize=7,
                    transform=ccrs.PlateCarree(), zorder=7)
    ax.plot([p['lon'] for p in ascent], [p['lat'] for p in ascent], color='#ffd54f',
            lw=1.6, transform=ccrs.PlateCarree(), zorder=5)
    ax.set_title(title, color='#e8f5fb', fontsize=11, pad=6)
    gl = ax.gridlines(linewidth=.3, color='#16394a', alpha=.6)
fig.suptitle('为什么分成两坨：对比度项把中间“正对晨光”的带压低了', color='#e8f5fb', fontsize=14, y=.99)
fig.subplots_adjust(left=.03, right=.98, top=.88, bottom=.03, wspace=.06)
fig.savefig(r'F:\DeepSeek工作区\_navwarn_verify\quality_contrast_compare.png', dpi=150,
            facecolor=fig.get_facecolor())
print('saved')

