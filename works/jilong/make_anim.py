# -*- coding: utf-8 -*-
"""高帧率过程动画：73 帧 @10 s，叠真实 DEM 晕渲，含流量标尺与三点标注。"""
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import matplotlib.animation as anim
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

B = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(B, 'mf_fine')
OUT = os.path.join(B, 'results')
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
fr = [(t, a[:, :, 4]) for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt'))]
print('%d 帧, t=%.0f..%.0f s' % (len(fr), fr[0][0], fr[-1][0]))

ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)

FPS = 15
fig, ax = plt.subplots(figsize=(11.5, 6.8))
fig.subplots_adjust(top=0.88, bottom=0.09, left=0.07, right=0.90)
ax.imshow(rgb, extent=[Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]], origin='upper', alpha=0.92)
mesh = ax.pcolormesh(Xg, Yg, np.zeros_like(Z), cmap='turbo', vmin=0, vmax=120,
                     shading='auto', alpha=0.9)
ax.plot(PORT[0], PORT[1], 'c*', ms=20, mec='k', label='Jilong port (arrival 510-540 s)')
ax.plot(SRC[0], SRC[1], 'wo', ms=10, mec='k', label='ice-avalanche source')
ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=10, mec='k', label='barrier lake (hit at 80 s)')
ax.set_aspect('equal'); ax.set_xlabel('E (km)'); ax.set_ylabel('N (km)')
ax.legend(loc='lower left', fontsize=9, framealpha=0.9)
cax = fig.add_axes([0.915, 0.16, 0.016, 0.66])
cb = fig.colorbar(mesh, cax=cax, label='flow depth H (m)')
tt = fig.suptitle('', fontsize=13, y=0.965)


def upd(i):
    t, H = fr[i]
    mesh.set_array(H.ravel())
    tt.set_text('Jilong ice avalanche 2026-08-26      t = %.0f s      H$_{max}$ = %.0f m'
                % (t, H.max()))
    return mesh, tt


an = anim.FuncAnimation(fig, upd, frames=len(fr), interval=1000 / FPS, blit=False)
p = os.path.join(OUT, 'jilong_animation_12fps.gif')
an.save(p, writer=anim.PillowWriter(fps=FPS))
plt.close(fig)
print('-> %s  (%.2f MB, %d 帧 @ %d fps)' % (p, os.path.getsize(p) / 1e6, len(fr), FPS))
