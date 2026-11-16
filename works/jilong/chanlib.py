# -*- coding: utf-8 -*-
"""
通用工具：为任意算例网格构建沟道曲线坐标 (s, n) 与 S_MAP。
用法: from chanlib import build_channel, s_map
"""
import os
import json
import numpy as np


def build_channel(run_dir, window_r=50, window_c=70, ns=800):
    """沿谷底追踪 源区->堰塞湖->口岸 的中心线，返回 s(E/N 平面上的弧长)。"""
    meta = json.load(open(os.path.join(run_dir, 'meta.json')))
    Z = np.load(os.path.join(run_dir, 'Z.npy')).astype('f8')
    NX, NY = meta['NX'], meta['NY']
    DX, DY = meta['DX'], meta['DY']
    E0, N0, N1 = meta['E0'], meta['N0'], meta['N1']
    sc, sr = int(round(meta['src_col'])), int(round(meta['src_row']))
    lc, lr = int(round(meta['lake_col'])), int(round(meta['lake_row']))
    pc, pr = int(round(meta['port_col'])), int(round(meta['port_row']))
    Af = np.where(Z > -1000, Z, np.nan)

    # 段1: 源区 -> 堰塞湖 (沿行方向)
    p1 = [(sr, sc)]
    c = sc
    step = -1 if lr < sr else 1
    for r in range(sr + step, lr + step, step):
        c0, c1 = max(0, c - window_r), min(NX, c + window_r + 1)
        seg = Af[r, c0:c1]
        if np.isfinite(seg).any():
            c = int(np.nanargmin(seg)) + c0
        p1.append((r, c))
    # 段2: 堰塞湖 -> 口岸 (沿列方向)
    p2 = []
    c = lc
    step = -1 if pc < lc else 1
    for cc in range(lc + step, pc + step, step):
        r0, r1 = max(0, lr - window_c), min(NY, lr + window_c + 1)
        seg = Af[r0:r1, cc]
        if np.isfinite(seg).any():
            r = int(np.nanargmin(seg)) + r0
            p2.append((r, cc))
    full = p1 + p2
    pts = np.array([[c * DX, -r * DY] for r, c in full], float)
    seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    s = np.concatenate([[0], np.cumsum(seg)])
    si = np.linspace(0, s[-1], ns)
    xi = np.interp(si, s, pts[:, 0])
    yi = np.interp(si, s, pts[:, 1])
    return dict(meta=meta, s=si, x=xi, y=yi, sx=sc, sy=sr, lx=lc, ly=lr, px=pc, py=pr)


def make_s_map(ch, block=100):
    """为网格每点计算其到中心线的最近弧长 s (km)。"""
    meta = ch['meta']
    NX, NY = meta['NX'], meta['NY']
    DX, DY = meta['DX'], meta['DY']
    xi, yi, si = ch['x'], ch['y'], ch['s']
    S = np.zeros((NY, NX), np.float32)
    for r0 in range(0, NY, block):
        r1 = min(NY, r0 + block)
        rr = np.arange(r0, r1)
        px = (np.arange(NX) * DX)[None, :, None]
        py = (-rr * DY)[:, None, None]
        d2 = (px - xi[None, None, :]) ** 2 + (py - yi[None, None, :]) ** 2
        k = np.argmin(d2, axis=2)
        S[r0:r1] = si[k]
    return S / 1000.0
