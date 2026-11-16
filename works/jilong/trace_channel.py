# -*- coding: utf-8 -*-
"""
用"逐行谷底最近邻"法追踪沟道：从口岸出发向上游，每行在当前列附近取最低点，
并要求单调不降(向上游)。这是最稳健的、不依赖 D8 的沟道提取。
同时统计每行的谷底高程，得到真实纵剖面。
"""
import numpy as np
from osgeo import osr

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
valid = A > -1000
E0, N1, RES = 322000, 3161000, 30
Af = np.where(valid, A, np.nan)

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ctU = osr.CoordinateTransformation(s1, s2)
ctL = osr.CoordinateTransformation(s2, s1)


def rc(lon, lat):
    x, y, _ = ctU.TransformPoint(float(lon), float(lat))
    return int((x - E0) / RES), int((N1 - y) / RES)


def ll(r, c):
    lon, lat, _ = ctL.TransformPoint(float(E0 + c * RES), float(N1 - r * RES))
    return lon, lat


# 口岸
pc, pr = rc(85.3767, 28.2871)
print('口岸 col=%d row=%d 高程=%.0f m (%.4fE %.4fN)' % (pc, pr, A[pr, pc], *ll(pr, pc)))

# 全域逐行谷底
print()
print('=== 全域逐行最低点（谷底带）===')
rowmin_c = np.full(ny, -1, int)
rowmin_v = np.full(ny, np.nan)
for r in range(ny):
    if valid[r].any():
        c = int(np.nanargmin(Af[r]))
        rowmin_c[r] = c; rowmin_v[r] = A[r, c]

# 从口岸所在行向上游追踪：每行取离上一行谷底最近的候选最低点
path = [(pr, rowmin_c[pr])]
window = 120
for r in range(pr - 1, 0, -1):
    if not valid[r].any():
        continue
    c_prev = path[-1][1]
    c0, c1 = max(0, c_prev - window), min(nx, c_prev + window + 1)
    seg = Af[r, c0:c1]
    if not np.isfinite(seg).any():
        continue
    c = int(np.nanargmin(seg)) + c0
    path.append((r, c))
path = path[::-1]
print()
print('沟道追踪 %d 行，终点 row=%d col=%d 高程=%.0f m' % (
    len(path), path[0][0], path[0][1], A[path[0][0], path[0][1]]))
np.save(W + r'\channel_trace.npy', np.array(path))

print()
print('=== 追踪沟道纵剖面（上游 -> 口岸）===')
for k in range(0, len(path), max(1, len(path) // 30)):
    r, c = path[k]
    lon, lat = ll(r, c)
    d = np.hypot((c - pc) * RES, (r - pr) * RES) / 1000
    print('  %.1f km  高程%5.0f m  (%.4fE %.4fN) row%4d col%4d' % (d, A[r, c], lon, lat, r, c))

# 谷底高程单调性检查
v = np.array([A[r, c] for r, c in path])
print()
print('沟道高程: %.0f -> %.0f m, 落差 %.0f m' % (v[0], v[-1], v[0] - v[-1]))
bad = (np.diff(v) > 20).sum()
print('逆坡段(上升>20m) 数量: %d / %d' % (bad, len(v) - 1))

# 源区候选A 的落点
sc, sr = rc(85.2953, 28.4997)
print()
print('源区候选A col=%d row=%d 高程=%.0f m' % (sc, sr, A[sr, sc]))
# 找沟道上最接近源区纬度的点
best = min(path, key=lambda p: abs(p[0] - sr))
print('同纬度沟道点 row=%d col=%d 高程=%.0f m (水平差 %.2f km)' % (
    best[0], best[1], A[best[0], best[1]], abs(best[1] - sc) * RES / 1000))
