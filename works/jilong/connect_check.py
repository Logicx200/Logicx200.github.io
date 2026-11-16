# -*- coding: utf-8 -*-
"""
从口岸沿谷底向西-北追踪真实河道，检查是否经过堰塞湖并上溯到源区。
"""
import numpy as np
from osgeo import osr

W = r'F:\DeepSeek工作区\jilong'
Z = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = Z.shape
GE0, GN1, GRES = 322000.0, 3161000.0, 30.0
valid = Z > -1000
Af = np.where(valid, Z, np.nan)

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ctU = osr.CoordinateTransformation(s1, s2)
ctL = osr.CoordinateTransformation(s2, s1)


def rc(lon, lat):
    x, y, _ = ctU.TransformPoint(float(lon), float(lat))
    return int((x - GE0) / GRES), int((GN1 - y) / GRES)


def ll(r, c):
    lon, lat, _ = ctL.TransformPoint(float(GE0 + c * GRES), float(GN1 - r * GRES))
    return lon, lat


PORT = rc(85.37793159, 28.27947783)
LAKE = rc(85.48521996, 28.33256414)
SRC = rc(85.51225662, 28.29062626)
pc, pr = PORT
print('口岸 col%d row%d' % (pc, pr))

# 从口岸逐行向西追踪（每行取最低，向东搜索窗口）
print()
print('=== 从口岸向南/北两端追踪主沟道（逐行取最低） ===')
for direction, label in [(-1, '向北'), (1, '向南')]:
    c = pc
    path = [(pr, c)]
    rng = range(pr, -1, direction) if direction < 0 else range(pr, ny, direction)
    for r in rng:
        c0, c1 = max(0, c - 80), min(nx, c + 80)
        seg = Af[r, c0:c1]
        if not np.isfinite(seg).any():
            continue
        c = int(np.nanargmin(seg)) + c0
        path.append((r, c))
    d = sum(np.hypot((path[i][1] - path[i - 1][1]) * GRES,
                     (path[i][0] - path[i - 1][0]) * GRES) for i in range(1, len(path)))
    print('  %s: %d 行, 沿程 %.2f km, 终点 row%d col%d (%.4fE %.4fN) %.0f m'
          % (label, len(path), d / 1000, path[-1][0], path[-1][1], *ll(*path[-1]), Z[path[-1]]))

# 关键: 检查 口岸 -> 堰塞湖 的连通性（同一条谷底）
print()
print('=== 口岸 -> 堰塞湖 连线谷底剖面 ===')
lc, lr = LAKE
N = 20
for i in range(N + 1):
    t = i / N
    r = int(pr + (lr - pr) * t); c = int(pc + (lc - pc) * t)
    r0, r1 = max(0, r - 15), min(ny, r + 16)
    c0, c1 = max(0, c - 15), min(nx, c + 16)
    blk = Af[r0:r1, c0:c1]
    v = np.nanmin(blk) if np.isfinite(blk).any() else np.nan
    print('  t=%.2f  col%4d row%4d  (%.4fE %.4fN)  谷底 %6.0f m' % (t, c, r, *ll(r, c), v))

print()
print('=== 堰塞湖 -> 源区 连线谷底剖面 ===')
sc, sr = SRC
for i in range(N + 1):
    t = i / N
    r = int(lr + (sr - lr) * t); c = int(lc + (sc - lc) * t)
    r0, r1 = max(0, r - 15), min(ny, r + 16)
    c0, c1 = max(0, c - 15), min(nx, c + 16)
    blk = Af[r0:r1, c0:c1]
    v = np.nanmin(blk) if np.isfinite(blk).any() else np.nan
    print('  t=%.2f  col%4d row%4d  (%.4fE %.4fN)  谷底 %6.0f m' % (t, c, r, *ll(r, c), v))

print()
print('=== 源区周边 5km 内高海拔(>=4800m)冰面分布 ===')
sc0, sr0 = SRC
R = int(5000 / GRES)
r0, r1 = max(0, sr0 - R), min(ny, sr0 + R + 1)
c0, c1 = max(0, sc0 - R), min(nx, sc0 + R + 1)
blk = Af[r0:r1, c0:c1]
for thr in (4000, 4500, 4800, 5000, 5200):
    m = blk >= thr
    print('  >=%d m: %5d 像元 (%.2f km2)' % (thr, m.sum(), m.sum() * 900 / 1e6))
print('  窗口高程范围 %.0f .. %.0f' % (np.nanmin(blk), np.nanmax(blk)))
# 窗口内最高点
k = np.unravel_index(np.nanargmax(blk), blk.shape)
nr, ncc = r0 + k[0], c0 + k[1]
print('  窗口最高 %.0f m @ col%d row%d (%.4fE %.4fN) 距源区点 %.2f km'
      % (blk[k], ncc, nr, *ll(nr, ncc), np.hypot((ncc - sc0) * GRES, (nr - sr0) * GRES) / 1000))
