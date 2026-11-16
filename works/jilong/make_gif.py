# -*- coding: utf-8 -*-
"""
把 MassFlow 结果做成过程动画 GIF（叠在真实 DEM 晕渲上）。
"""
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

BASE = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(BASE, 'results')
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(os.path.join(BASE, 'mf_run2', 'meta.json')))
Z = np.load(os.path.join(BASE, 'mf_run2', 'Z.npy'))
DX, DY, NX, NY = meta['DX'], meta['DY'], meta['NX'], meta['NY']
Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                     (meta['N1'] - np.arange(NY) * DY) / 1000.0)
PORT = (340873 / 1000, 3129127 / 1000)
SRC = (333156 / 1000, 3153743 / 1000)


def make_gif(tag, path, fps=4, vmax=90.0):
    fr = [(t, a) for t, a in iter_zones(path)]
    if not fr:
        print('无数据'); return
    print('%s: %d 帧' % (tag, len(fr)))
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)

    fig, ax = plt.subplots(figsize=(6.6, 8.6))
    ax.imshow(rgb, extent=[Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]],
              origin='upper', alpha=0.9)
    mesh = ax.pcolormesh(Xg, Yg, np.zeros_like(Z), cmap='turbo',
                         vmin=0, vmax=vmax, shading='auto', alpha=0.92)
    ax.plot(PORT[0], PORT[1], 'c*', ms=16, mec='k', label='Jilong port')
    ax.plot(SRC[0], SRC[1], 'wo', ms=9, mec='k', label='source')
    ax.legend(loc='lower left', fontsize=8)
    ax.set_aspect('equal')
    ax.set_xlabel('E (km)'); ax.set_ylabel('N (km)')
    tt = ax.set_title('')
    fig.colorbar(mesh, ax=ax, shrink=0.75, label='flow depth H (m)')

    def upd(i):
        t, a = fr[i]
        H = a[:, :, 4]
        mesh.set_array(H.ravel())
        tt.set_text('Jilong ice avalanche   t = %.0f s   (H max %.0f m)' % (t, H.max()))
        return mesh, tt

    an = anim.FuncAnimation(fig, upd, frames=len(fr), interval=1000 / fps, blit=False)
    p = os.path.join(OUT, '%s_animation.gif' % tag)
    an.save(p, writer=anim.PillowWriter(fps=fps))
    plt.close(fig)
    print('->', p, '(%.1f MB)' % (os.path.getsize(p) / 1e6))


if __name__ == '__main__':
    tag = sys.argv[1] if len(sys.argv) > 1 else 'baseline_mu015'
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'mf_run2', 'output1_region1.plt')
    make_gif(tag, path)
