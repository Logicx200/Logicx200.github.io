# -*- coding: utf-8 -*-
"""修正模型的最终出图：流场叠真实 DEM，标注源区/堰塞湖/口岸。"""
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
RUN = os.path.join(B, 'mf_real')
OUT = os.path.join(B, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(os.path.join(RUN, 'meta.json')))
Z = np.load(os.path.join(RUN, 'Z.npy'))
DX, DY, NX, NY = meta['DX'], meta['DY'], meta['NX'], meta['NY']
Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                     (meta['N1'] - np.arange(NY) * DY) / 1000.0)
SRC = ((meta['E0'] + meta['src_col'] * DX) / 1000, (meta['N1'] - meta['src_row'] * DY) / 1000)
LAKE = ((meta['E0'] + meta['lake_col'] * DX) / 1000, (meta['N1'] - meta['lake_row'] * DY) / 1000)
PORT = ((meta['E0'] + meta['port_col'] * DX) / 1000, (meta['N1'] - meta['port_row'] * DY) / 1000)

path = os.path.join(RUN, 'output1_region1.plt')
fr = [(t, a) for t, a in iter_zones(path)]
print('%d 帧' % len(fr))

ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)

sel = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
sel = [i for i in sel if i < len(fr)]
cols = 4
rows = int(np.ceil(len(sel) / cols))
fig, axes = plt.subplots(rows, cols, figsize=(4.6 * cols, 3.9 * rows), squeeze=False)
for k, i in enumerate(sel):
    t, a = fr[i]
    H = a[:, :, 4]
    ax = axes[k // cols][k % cols]
    ax.imshow(rgb, extent=[Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]],
              origin='upper', alpha=0.9)
    m = ax.pcolormesh(Xg, Yg, H, cmap='turbo', vmin=0, vmax=120, shading='auto', alpha=0.9)
    ax.plot(PORT[0], PORT[1], 'c*', ms=17, mec='k')
    ax.plot(SRC[0], SRC[1], 'wo', ms=9, mec='k')
    ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=8, mec='k')
    ax.set_title('t = %.0f s    Hmax %.0f m' % (t, H.max()), fontsize=10)
    ax.set_aspect('equal'); ax.tick_params(labelsize=7)
for k in range(len(sel), rows * cols):
    axes[k // cols][k % cols].axis('off')
fig.colorbar(m, ax=axes, shrink=0.5, label='flow depth H (m)')
fig.suptitle('Jilong ice avalanche 2026-08-26  -  corrected flow path (mu=0.005)', fontsize=13)
p1 = os.path.join(OUT, 'real_sequence.png')
fig.savefig(p1, dpi=115, bbox_inches='tight'); plt.close(fig)
print('->', p1)

# 最终堆积 + 过程最大厚度
t, a = fr[-1]
fig, axs = plt.subplots(1, 2, figsize=(16, 5.4))
for ax, fld, ttl in [(axs[0], a[:, :, 7], 'peak depth Hmax (t=%.0f s)' % t),
                     (axs[1], a[:, :, 4], 'final depth H (t=%.0f s)' % t)]:
    ax.imshow(rgb, extent=[Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]], origin='upper', alpha=0.9)
    im = ax.pcolormesh(Xg, Yg, fld, cmap='turbo', shading='auto', alpha=0.9)
    ax.plot(PORT[0], PORT[1], 'c*', ms=18, mec='k', label='Jilong port')
    ax.plot(SRC[0], SRC[1], 'wo', ms=9, mec='k', label='source')
    ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=9, mec='k', label='barrier lake')
    ax.set_title(ttl); ax.set_aspect('equal'); ax.legend(fontsize=8, loc='lower right')
    fig.colorbar(im, ax=ax, shrink=0.85, label='m')
p2 = os.path.join(OUT, 'real_final.png')
fig.savefig(p2, dpi=115, bbox_inches='tight'); plt.close(fig)
print('->', p2)
