# -*- coding: utf-8 -*-
"""One figure per wavelength band, x-axis in wavelength (micrometres).

Each figure has two stacked panels sharing the wavelength axis:
  (a) total slant-path transmittance
  (b) partial transmittance of H2O, CO2 and CH4
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, 'figures')
os.makedirs(OUTDIR, exist_ok=True)

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'font.size': 10.5,
    'axes.linewidth': 0.9,
    'savefig.dpi': 300,
})

C = dict(tr_total='#111111', tr_H2O='#1f6fd0', tr_CO2='#d62728', tr_CH4='#2ca02c')
LAB = dict(tr_total='总透过率', tr_H2O='H$_2$O', tr_CO2='CO$_2$', tr_CH4='CH$_4$')


def band_figure(npz, outname, title, wl_ticks, features=()):
    d = np.load(os.path.join(BASE, npz))
    nu = d['grid']
    wl = 1e4 / nu
    order = np.argsort(wl)          # ascending wavelength
    wl = wl[order]
    step_nu = float(nu[1] - nu[0])

    fig, axes = plt.subplots(2, 1, figsize=(11.6, 7.6), sharex=True,
                             gridspec_kw=dict(height_ratios=[1, 1], hspace=0.26,
                                              left=0.085, right=0.975, top=0.87,
                                              bottom=0.085))

    # ---- (a) total ----
    ax = axes[0]
    y = d['tr_total'][order]
    ax.fill_between(wl, 0, y, color='#9aa4b0', alpha=0.35, lw=0)
    ax.plot(wl, y, color=C['tr_total'], lw=0.9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel('总透过率  $T$')
    ax.grid(alpha=0.25, lw=0.5)
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax.text(0.008, 0.95, '(a) 总斜程透过率', transform=ax.transAxes, fontsize=10.5,
            fontweight='bold', va='top',
            bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=1.6))
    meanT = float(np.trapezoid(y, wl) / (wl[-1] - wl[0]))
    ax.text(0.992, 0.95, '波段平均 $T$ = %.3f' % meanT, transform=ax.transAxes,
            fontsize=9, va='top', ha='right',
            bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=2))
    for w0, txt in features:
        ax.annotate(txt, xy=(w0, 0.05), xytext=(w0, 0.55), ha='center', fontsize=8.5,
                    color='#333333',
                    bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=1.2),
                    arrowprops=dict(arrowstyle='-', lw=0.7, color='#777777',
                                    shrinkA=1, shrinkB=2))

    # ---- (b) individual gases ----
    ax2 = axes[1]
    for key in ('tr_H2O', 'tr_CO2', 'tr_CH4'):
        ax2.plot(wl, d[key][order], color=C[key], lw=0.65, alpha=0.92, label=LAB[key])
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel('分气体透过率  $T_i$')
    ax2.set_xlabel('波长 (μm)')
    ax2.grid(alpha=0.25, lw=0.5)
    ax2.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.10), ncol=3,
               fontsize=9, frameon=False)
    ax2.text(0.008, 0.95, '(b) 各气体分透过率', transform=ax2.transAxes, fontsize=10.5,
             fontweight='bold', va='top',
             bbox=dict(facecolor='white', alpha=0.75, edgecolor='none', pad=1.6))

    for a in axes:
        a.set_xlim(wl[0], wl[-1])
    axes[0].set_xticks(wl_ticks)
    axes[0].set_xticklabels(['%g' % t for t in wl_ticks])

    sec = axes[0].secondary_xaxis('top', functions=(lambda w: 1e4 / np.maximum(w, 1e-9),
                                                    lambda v: 1e4 / np.maximum(v, 1e-6)))
    sec.set_xlabel('波数 (cm$^{-1}$)', labelpad=2)

    fig.suptitle(title + '   （%g cm$^{-1}$ 分辨率）' % step_nu, fontsize=12, y=0.965)
    png = os.path.join(OUTDIR, outname + '.png')
    fig.savefig(png)
    fig.savefig(png.replace('.png', '.pdf'))
    plt.close(fig)
    print('saved', png, ' mean T=%.3f' % meanT)


if __name__ == '__main__':
    band_figure('slant_band_2_3um.npz', 'band1_2-3um_SWIR',
                '① 2–3 μm 短波红外斜程透过率（8 km 平台 / 20 km 地面，斜程 21.54 km）',
                [2.0, 2.2, 2.4, 2.6, 2.8, 3.0],
                [(2.7, 'H$_2$O 2.7 μm'), (2.3, 'CH$_4$ 2.3 μm')])

    band_figure('slant_zoom_3_5.npz', 'band2_3-5um_MWIR',
                '② 3–5 μm 中波红外斜程透过率',
                [3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0],
                [(4.3, 'CO$_2$ 4.3 μm'), (3.3, 'CH$_4$ 3.3 μm')])

    band_figure('slant_band_5_8um.npz', 'band3_5-8um',
                '③ 5–8 μm 中红外斜程透过率',
                [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0],
                [(6.3, 'H$_2$O 6.3 μm'), (7.7, 'CH$_4$ 7.7 μm')])

    band_figure('slant_zoom_8_14.npz', 'band4_8-14um_LWIR',
                '④ 8–14 μm 长波红外窗口斜程透过率',
                [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0],
                [])

    band_figure('slant_band_14_20um.npz', 'band5_14-20um',
                '⑤ 14–20 μm 远红外斜程透过率',
                [14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
                [(15.0, 'CO$_2$ 15 μm')])
