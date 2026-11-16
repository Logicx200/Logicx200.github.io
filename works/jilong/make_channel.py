# -*- coding: utf-8 -*-
"""
在模型网格上重建弯曲沟道中心线，建立 (s, n) 曲线坐标：
  s = 沿程距离（源区 -> 堰塞湖 -> 口岸，沿谷底）
  n = 横向距离
用于输出纵剖面剖面与横断面。
"""
import os
import json
import numpy as np

B = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(B, 'mf_real')
meta = json.load(open(os.path.join(RUN, 'meta.json')))
Z = np.load(os.path.join(RUN, 'Z.npy')).astype('f8')
NX, NY = meta['NX'], meta['NY']
DX, DY = meta['DX'], meta['DY']
E0, N0, N1 = meta['E0'], meta['N0'], meta['N1']
sc, sr = int(round(meta['src_col'])), int(round(meta['src_row']))
lc, lr = int(round(meta['lake_col'])), int(round(meta['lake_row']))
pc, pr = int(round(meta['port_col'])), int(round(meta['port_row']))
valid = Z > -1000
Af = np.where(valid, Z, np.nan)
print('网格 %dx%d  dx=%.0f dy=%.0f' % (NX, NY, DX, DY))
print('源区(%.0f,%.0f) 堰塞湖(%.0f,%.0f) 口岸(%.0f,%.0f)' % (sc, sr, lc, lr, pc, pr))


def trace_rows(c_start, r_start, r_end, window=70):
    """从 (c_start,r_start) 逐行向 r_end 方向取谷底最低点"""
    path = [(r_start, c_start)]
    c = c_start
    step = 1 if r_end > r_start else -1
    for r in range(int(r_start) + step, int(r_end) + step, step):
        c0, c1 = max(0, c - window), min(NX, c + window + 1)
        seg = Af[r, c0:c1]
        if not np.isfinite(seg).any():
            continue
        c = int(np.nanargmin(seg)) + c0
        path.append((r, c))
    return path


# 段1: 源区 -> 堰塞湖 (向北)
p1 = trace_rows(sc, sr, lr)
# 段2: 堰塞湖 -> 口岸 (逐行向南到口岸行, 但口岸在西南; 改用逐列向西)
path2 = []
c = lc
for cc in range(int(lc), int(pc) - 1, -1):
    r0, r1 = max(0, int(lr) - 70), min(NY, int(lr) + 71)
    seg = Af[r0:r1, cc]
    if not np.isfinite(seg).any():
        continue
    r = int(np.nanargmin(seg)) + r0
    path2.append((r, cc))
print('段1(源区->湖) %d 点, 段2(湖->口岸) %d 点' % (len(p1), len(path2)))

full = p1 + path2
pts = np.array([[c * DX, -r * DY] for r, c in full], dtype=float)  # 用 (E, -N) 便于计算
seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
s = np.concatenate([[0], np.cumsum(seg)])
print('中心线总长 %.2f km, 点数 %d' % (s[-1] / 1000, len(pts)))

# 平滑重采样为等间距
L = s[-1]
NS = 600
si = np.linspace(0, L, NS)
xi = np.interp(si, s, pts[:, 0])
yi = np.interp(si, s, pts[:, 1])
np.savez(os.path.join(B, 'channel_sn.npz'), s=si, x=xi, y=yi,
         rows=np.array([p[0] for p in full]), cols=np.array([p[1] for p in full]))

# 与三个锚点的距离校验
for nm, (cc, rr) in [('源区', (sc, sr)), ('堰塞湖', (lc, lr)), ('口岸', (pc, pr))]:
    d = np.hypot(xi - cc * DX, yi - (-rr * DY))
    k = int(np.argmin(d))
    print('  %-4s 距中心线最近 %.2f km (s=%.2f km)' % (nm, d[k] / 1000, si[k] / 1000))
