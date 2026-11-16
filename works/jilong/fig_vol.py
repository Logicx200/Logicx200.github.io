# -*- coding: utf-8 -*-
"""体积标定对比图：前缘距离-时间曲线 + 最终堆积对比。"""
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

B = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(B, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
Z = np.load(os.path.join(B, 'mf_real', 'Z.npy'))
DX, DY = meta['DX'], meta['DY']
NX, NY = meta['NX'], meta['NY']
sc, pc, pr = int(round(meta['src_col'])), int(round(meta['port_col'])), int(round(meta['port_row']))
lc, lr = int(round(meta['lake_col'])), int(round(meta['lake_row']))
Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                     (meta['N1'] - np.arange(NY) * DY) / 1000.0)
PORTX, PORTY = Xg[pr, pc], Yg[pr, pc]

RUNS = [('50', os.path.join(B, 'mf_vol', 'v050', 'output1_region1.plt')),
        ('70', os.path.join(B, 'mf_long', 'output1_region1.plt')),
        ('100', os.path.join(B, 'mf_vol', 'v100', 'output1_region1.plt')),
        ('140', os.path.join(B, 'mf_vol', 'v140', 'output1_region1.plt'))]

fig, ax = plt.subplots(figsize=(8.2, 5.2))
final = []
for lab, p in RUNS:
    if not os.path.exists(p):
        continue
    ts, ds, last = [], [], None
    for t, a in iter_zones(p):
        H = a[:, :, 4]
        wet = H > 0.05
        cc = np.where(wet.any(axis=0))[0]
        if cc.size == 0:
            continue
        km = (sc - int(cc.min())) * DX / 1000
        ts.append(t); ds.append(km)
        last = (t, H)
    ax.plot(ts, ds, lw=2, label='V0 = %s x10$^6$ m$^3$' % lab)
    if last:
        final.append((lab, last[1]))

ax.axhline((sc - pc) * DX / 1000, color='c', ls='--', lw=2, label='Jilong port (13.20 km)')
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
ax.set_xlabel('time (s)'); ax.set_ylabel('front runout from source (km)')
ax.set_title('Volume calibration - front runout vs time')
ax.grid(alpha=0.3); ax.legend(fontsize=9)
p1 = os.path.join(OUT, 'calib_volume.png')
fig.savefig(p1, dpi=125, bbox_inches='tight'); plt.close(fig)
print('->', p1)

# 最终堆积对比
ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)
n = len(final)
fig, axs = plt.subplots(1, n, figsize=(5.4 * n, 4.6), squeeze=False)
for k, (lab, H) in enumerate(final):
    axx = axs[0][k]
    axx.imshow(rgb, extent=[Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]], origin='upper', alpha=0.9)
    m = axx.pcolormesh(Xg, Yg, H, cmap='turbo', vmin=0, vmax=100, shading='auto', alpha=0.9)
    axx.plot(PORTX, PORTY, 'c*', ms=16, mec='k')
    axx.set_title('V0 = %s x10$^6$ m$^3$' % lab, fontsize=10)
    axx.set_aspect('equal'); axx.tick_params(labelsize=7)
fig.colorbar(m, ax=axs, shrink=0.8, label='final depth H (m)')
fig.suptitle('Final deposit, different initial volumes (t = 1200 s)', fontsize=12)
p2 = os.path.join(OUT, 'calib_volume_final.png')
fig.savefig(p2, dpi=115, bbox_inches='tight'); plt.close(fig)
print('->', p2)
