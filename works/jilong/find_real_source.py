# -*- coding: utf-8 -*-
"""
以用户修正后的三个坐标为锚点，重建真实流路：
  1) 在源区点周边搜索高程 >= 4800/5000 m 的冰斗（对应文献"约5200m断裂"）
  2) 用逐行谷底追踪把 源区->堰塞湖->口岸 连成一条通路
  3) 输出沿程距离与落差
"""
import numpy as np
from osgeo import osr
from scipy import ndimage

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


SRC = rc(85.51225662, 28.29062626)
LAKE = rc(85.48521996, 28.33256414)
PORT = rc(85.37793159, 28.27947783)

print('=== 1) 源区点周边寻找高海拔冰斗 ===')
sc, sr = SRC
for rad_km in (3, 6, 10, 15):
    R = int(rad_km * 1000 / GRES)
    r0, r1 = max(0, sr - R), min(ny, sr + R + 1)
    c0, c1 = max(0, sc - R), min(nx, sc + R + 1)
    blk = Af[r0:r1, c0:c1]
    if not np.isfinite(blk).any():
        continue
    mx = np.nanmax(blk)
    k = np.unravel_index(np.nanargmax(blk), blk.shape)
    rr, cc = r0 + k[0], c0 + k[1]
    hi = blk >= 4800
    print('  半径 %2d km: 最高 %5.0f m @ col%d row%d (%.4fE %.4fN)   >=4800m 占 %.1f%%'
          % (rad_km, mx, cc, rr, *ll(rr, cc), 100 * np.nanmean(hi)))

print()
print('=== 2) 全域 >=5000m 连通块（找冰斗）===')
hi = Af >= 5000
lab, n = ndimage.label(hi)
sizes = ndimage.sum(hi, lab, range(1, n + 1))
order = np.argsort(sizes)[::-1]
for k in order[:10]:
    m = (lab == k + 1)
    rr, cc = np.where(m)
    # 距源区点距离
    d = np.hypot((cc - sc) * GRES, (rr - sr) * GRES).min() / 1000
    print('  块%3d %6d 像元 %5.1f km2  最高%5.0f m  中心 %.4fE %.4fN  距源区点最近 %.2f km'
          % (k + 1, sizes[k], sizes[k] * 900 / 1e6, np.nanmax(Af[rr, cc]),
             *ll(int(rr.mean()), int(cc.mean())), d))

print()
print('=== 3) 堰塞湖周边地形（确认是否为洼地）===')
lc, lr = LAKE
R = 40
blk = Af[lr - R:lr + R, lc - R:lc + R]
print('  堰塞湖点 %.0f m, 周边 %d 格内最低 %.0f m, 最高 %.0f m'
      % (Z[lr, lc], R, np.nanmin(blk), np.nanmax(blk)))
# 是否有闭合洼地
low = blk < Z[lr, lc] + 30
print('  低于(点+30m) 的像元 %d / %d' % (low.sum(), blk.size))

print()
print('=== 4) 源区->堰塞湖 逐行谷底通路 ===')
path = []
c = sc
for r in range(sr, lr - 1, -1):
    c0, c1 = max(0, c - 60), min(nx, c + 60)
    seg = Af[r, c0:c1]
    if not np.isfinite(seg).any():
        continue
    c = int(np.nanargmin(seg)) + c0
    path.append((r, c))
print('  追踪 %d 行, 终点 row%d col%d (%.4fE %.4fN) %.0f m'
      % (len(path), path[-1][0], path[-1][1], *ll(*path[-1]), Z[path[-1]]))
d = 0.0
for i in range(1, len(path)):
    d += np.hypot((path[i][1] - path[i - 1][1]) * GRES, (path[i][0] - path[i - 1][0]) * GRES)
print('  沿程 %.2f km, 落差 %.0f m' % (d / 1000, Z[path[0]] - Z[path[-1]]))
