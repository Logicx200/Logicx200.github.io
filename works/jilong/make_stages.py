# -*- coding: utf-8 -*-
"""
分阶段模拟图（核心交付）：
 (A) 阶段网格图：16 个关键时刻，每个是一个独立的面板，标题完整
 (B) 全帧接触表：全部 73 帧 @10 s，一图纵览
所有图用 subplots_adjust 预留标题空间，避免被裁。
"""
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
RUN = os.path.join(B, 'mf_fine')
OUT = os.path.join(B, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
Z = np.load(os.path.join(B, 'mf_real', 'Z.npy'))
NX, NY = meta['NX'], meta['NY']
DX, DY = meta['DX'], meta['DY']
Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                     (meta['N1'] - np.arange(NY) * DY) / 1000.0)
SRC = (Xg[int(round(meta['src_row'])), int(round(meta['src_col']))],
       Yg[int(round(meta['src_row'])), int(round(meta['src_col']))])
LAKE = (Xg[int(round(meta['lake_row'])), int(round(meta['lake_col']))],
        Yg[int(round(meta['lake_row'])), int(round(meta['lake_col']))])
PORT = (Xg[int(round(meta['port_row'])), int(round(meta['port_col']))],
        Yg[int(round(meta['port_row'])), int(round(meta['port_col']))])

print('读取帧...')
frames = [(t, a[:, :, 4]) for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt'))]
print('%d 帧 t=%.0f..%.0f' % (len(frames), frames[0][0], frames[-1][0]))

ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)
EXT = [Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]]


def pick(t_target):
    return min(range(len(frames)), key=lambda i: abs(frames[i][0] - t_target))


def draw(ax, idx, title, vmax=120, small=False):
    t, H = frames[idx]
    ax.imshow(rgb, extent=EXT, origin='upper', alpha=0.92)
    m = ax.pcolormesh(Xg, Yg, np.where(H > 0.05, H, np.nan), cmap='turbo',
                      vmin=0, vmax=vmax, shading='auto', alpha=0.92)
    ax.plot(PORT[0], PORT[1], 'c*', ms=11 if small else 17, mec='k')
    ax.plot(SRC[0], SRC[1], 'wo', ms=6 if small else 9, mec='k')
    ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=6 if small else 9, mec='k')
    ax.set_title(title, fontsize=8.5 if small else 11, pad=4)
    ax.set_aspect('equal')
    ax.tick_params(labelsize=6 if small else 8)
    return m


# ================= (A) 阶段网格图 =================
STAGES = [0, 20, 50, 80, 100, 150, 200, 250, 300, 350, 400, 450, 500, 540, 600, 720]
cols, rows = 4, 4
fig, axes = plt.subplots(rows, cols, figsize=(4.3 * cols, 3.3 * rows + 1.1))
m = None
for k, st in enumerate(STAGES):
    ax = axes[k // cols][k % cols]
    idx = pick(st)
    t, H = frames[idx]
    note = ''
    if st == 80:
        note = '  <- reaches barrier lake'
    if st in (500, 540):
        note = '  <- reaches Jilong port'
    m = draw(ax, idx, 't = %.0f s    H$_{max}$ = %.0f m%s' % (t, H.max(), note))
for k in range(len(STAGES), rows * cols):
    axes[k // cols][k % cols].axis('off')
fig.subplots_adjust(top=0.93, bottom=0.06, left=0.03, right=0.90,
                    hspace=0.32, wspace=0.16)
cax = fig.add_axes([0.915, 0.18, 0.015, 0.62])
fig.colorbar(m, cax=cax, label='flow depth H (m)')
fig.suptitle('Jilong ice avalanche 2026-08-26  -  simulation stages\n'
             '(white dot: source   magenta square: barrier lake   cyan star: Jilong port)',
             fontsize=13, y=0.985)
p = os.path.join(OUT, 'stages_grid.png')
fig.savefig(p, dpi=115)
plt.close(fig)
print('->', p)

# ================= (B) 全帧接触表 =================
n = len(frames)
cc = 9
rr = int(np.ceil(n / cc))
fig, axes = plt.subplots(rr, cc, figsize=(2.05 * cc, 1.72 * rr + 0.9))
for k in range(rr * cc):
    ax = axes[k // cc][k % cc]
    if k >= n:
        ax.axis('off'); continue
    t, H = frames[k]
    m = draw(ax, k, '%.0f s' % t, small=True)
    ax.set_xticks([]); ax.set_yticks([])
fig.subplots_adjust(top=0.94, bottom=0.02, left=0.01, right=0.90,
                    hspace=0.18, wspace=0.05)
cax = fig.add_axes([0.915, 0.15, 0.012, 0.7])
fig.colorbar(m, cax=cax, label='H (m)')
fig.suptitle('All 73 output frames (10 s interval)  -  Jilong ice avalanche', fontsize=13, y=0.985)
p2 = os.path.join(OUT, 'stages_contact_sheet.png')
fig.savefig(p2, dpi=125)
plt.close(fig)
print('->', p2)
