# -*- coding: utf-8 -*-
"""
从 MassFlow 结果出图：流体厚度 H 的逐时刻演化图 + 最终堆积厚度图。
利用输出文件自带的 X/Y 坐标，不受各向异性影响。
"""
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

BASE = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(BASE, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)


def load_frames(plt, limit=None):
    fr = []
    for t, a in iter_zones(plt):
        X = a[0, :, 0]
        Y = a[:, 0, 1]
        fr.append((t, X, Y, a))
        if limit and len(fr) >= limit:
            break
    return fr


def plot_run(tag, plt_file, title, vmax=120.0, max_frames=16):
    fr = load_frames(plt_file)
    if not fr:
        print('  %s 无数据' % tag); return
    if len(fr) > max_frames:
        idx = np.linspace(0, len(fr) - 1, max_frames).round().astype(int)
        fr = [fr[i] for i in idx]
    n = len(fr)
    print('  %s: %d 帧' % (tag, n))
    # 总览图
    cols = min(4, n)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.2 * rows), squeeze=False)
    for k, (t, X, Y, a) in enumerate(fr):
        ax = axes[k // cols][k % cols]
        H = a[:, :, 4]
        m = ax.pcolormesh(X / 1000.0, Y / 1000.0, H, cmap='turbo',
                          vmin=0, vmax=vmax, shading='auto')
        ax.set_title('t = %.0f s   Hmax=%.0f m' % (t, H.max()), fontsize=9)
        ax.set_aspect('equal')
        ax.tick_params(labelsize=7)
    for k in range(n, rows * cols):
        axes[k // cols][k % cols].axis('off')
    fig.colorbar(m, ax=axes, shrink=0.6, label='H (m)')
    fig.suptitle(title, fontsize=12)
    p1 = os.path.join(OUT, '%s_sequence.png' % tag)
    fig.savefig(p1, dpi=110, bbox_inches='tight')
    plt.close(fig)
    print('    -> %s' % p1)

    # 最终堆积图（用 Hmax 表示过程最大厚度，以及末态 H）
    t, X, Y, a = fr[-1]
    fig, axs = plt.subplots(1, 3, figsize=(16, 5))
    axs[0].pcolormesh(X / 1000, Y / 1000, a[:, :, 7], cmap='turbo', shading='auto')
    axs[0].set_title('Hmax 过程最大厚度 (t=%.0f s)' % t)
    im = axs[1].pcolormesh(X / 1000, Y / 1000, a[:, :, 4], cmap='turbo', shading='auto')
    axs[1].set_title('末态厚度 H')
    fig.colorbar(im, ax=axs[1], shrink=0.8, label='m')
    base = a[:, :, 3]
    dep = a[:, :, 3] - base
    axs[2].pcolormesh(X / 1000, Y / 1000, dep, cmap='turbo', shading='auto')
    axs[2].set_title('基底高程')
    for ax in axs:
        ax.set_aspect('equal'); ax.set_xlabel('E (km)'); ax.set_ylabel('N (km)')
    p2 = os.path.join(OUT, '%s_final.png' % tag)
    fig.savefig(p2, dpi=110, bbox_inches='tight')
    plt.close(fig)
    print('    -> %s' % p2)


if __name__ == '__main__':
    tag = sys.argv[1] if len(sys.argv) > 1 else 'mu_015'
    plt_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'mf_run2', 'output1_region1.plt')
    plot_run(tag, plt_path, 'Jilong ice avalanche - H field (%s)' % tag)
