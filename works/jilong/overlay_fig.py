# -*- coding: utf-8 -*-
"""
把 MassFlow 的流场叠在真实 DEM 晕渲上，验证流动是否沿真实河谷。
同时输出前缘对比图。
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

BASE = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(BASE, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(os.path.join(BASE, 'mf_run2', 'meta.json')))
Z = np.load(os.path.join(BASE, 'mf_run2', 'Z.npy'))
DX, DY, NX, NY = meta['DX'], meta['DY'], meta['NX'], meta['NY']
E0, N0 = meta['E0'], meta['N0']
# 输出文件的 Y 是从北向南递减
X = E0 + np.arange(NX) * DX
Y = (meta['N1']) - np.arange(NY) * DY[::-1][::-1] if False else None
Ygrid = (meta['N1']) - np.arange(NY) * DY

PORT_E, PORT_N = 340873.0, 3129127.0
SRC_E, SRC_N = 333156.0, 3153743.0


def frames(path):
    out = []
    for t, a in iter_zones(path):
        out.append((t, a[:, :, 4]))
    return out


def plot_overlay(tag, path, times=None, vmax=100.0):
    fr = frames(path)
    if not fr:
        print('无数据'); return
    ls = LightSource(azdeg=315, altdeg=45)
    Xg, Yg = np.meshgrid(X / 1000.0, Ygrid / 1000.0)
    rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft',
                   vert_exag=2, dx=DX, dy=DY)
    idx = list(range(len(fr)))
    if times:
        idx = [int(np.argmin([abs(fr[i][0] - tt) for i in range(len(fr))])) for tt in times]
    n = len(idx)
    cols = min(4, n); rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.5 * cols, 4.0 * rows), squeeze=False)
    for k, i in enumerate(idx):
        t, H = fr[i]
        ax = axes[k // cols][k % cols]
        ax.imshow(rgb, extent=[X[0] / 1000, X[-1] / 1000, Ygrid[-1] / 1000, Ygrid[0] / 1000],
                  origin='upper', alpha=0.85)
        m = ax.pcolormesh(Xg, Yg, H, cmap='turbo', vmin=0, vmax=vmax,
                          shading='auto', alpha=0.9)
        ax.plot(PORT_E / 1000, PORT_N / 1000, 'c*', ms=14, mec='k', label='Jilong port')
        ax.plot(SRC_E / 1000, SRC_N / 1000, 'wo', ms=8, mec='k', label='source')
        ax.set_title('t = %.0f s   (Hmax %.0f m)' % (t, H.max()), fontsize=10)
        ax.set_aspect('equal'); ax.tick_params(labelsize=7)
        if k == 0:
            ax.legend(fontsize=7, loc='lower left')
    for k in range(n, rows * cols):
        axes[k // cols][k % cols].axis('off')
    fig.colorbar(m, ax=axes, shrink=0.55, label='flow depth H (m)')
    fig.suptitle('Jilong ice avalanche on real DEM  -  %s' % tag, fontsize=13)
    p = os.path.join(OUT, '%s_overlay.png' % tag)
    fig.savefig(p, dpi=115, bbox_inches='tight')
    plt.close(fig)
    print('->', p)


if __name__ == '__main__':
    tag = sys.argv[1] if len(sys.argv) > 1 else 'mu_015'
    p = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'mf_run2', 'output1_region1.plt')
    plot_overlay(tag, p)
