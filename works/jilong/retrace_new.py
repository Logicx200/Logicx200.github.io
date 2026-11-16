# -*- coding: utf-8 -*-
"""
用用户修正后的坐标重新追踪沟道：
  源区 85.51225662,28.29062626
  堰塞湖 85.48521996,28.33256414
  口岸 85.37793159,28.27947783
输出真实沿程距离与落差，并检查流路连通性。
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
    return int((x - GE0) / GRES), int((GN1 - y) / GRES), x, y


def ll(r, c):
    lon, lat, _ = ctL.TransformPoint(float(GE0 + c * GRES), float(GN1 - r * GRES))
    return lon, lat


SRC = rc(85.51225662, 28.29062626)
LAKE = rc(85.48521996, 28.33256414)
PORT = rc(85.37793159, 28.27947783)
print('源区 col%d row%d 高程%.0f' % (SRC[0], SRC[1], Z[SRC[1], SRC[0]]))
print('堰塞湖 col%d row%d 高程%.0f' % (LAKE[0], LAKE[1], Z[LAKE[1], LAKE[0]]))
print('口岸 col%d row%d 高程%.0f' % (PORT[0], PORT[1], Z[PORT[1], PORT[0]]))
print()

# 邻域谷底（避免点位落在坡上）
def valley(c, r, half=20):
    c0, c1 = max(0, c - half), min(nx, c + half + 1)
    r0, r1 = max(0, r - half), min(ny, r + half + 1)
    blk = Af[r0:r1, c0:c1]
    k = np.unravel_index(np.nanargmin(blk), blk.shape)
    return c0 + k[1], r0 + k[0], blk[k]


sc, sr, sz = valley(*SRC[:2])
lc, lr, lz = valley(*LAKE[:2])
pc, pr, pz = valley(*PORT[:2])
print('各点邻域谷底:')
print('  源区谷底 col%d row%d  %.0f m (点位 %.0f)' % (sc, sr, sz, Z[SRC[1], SRC[0]]))
print('  堰塞湖底 col%d row%d  %.0f m (点位 %.0f)' % (lc, lr, lz, Z[LAKE[1], LAKE[0]]))
print('  口岸谷底 col%d row%d  %.0f m (点位 %.0f)' % (pc, pr, pz, Z[PORT[1], PORT[0]]))
print()

# 追踪：从口岸向西(上游) —— 注意新源区在口岸东侧
print('=== 从口岸沿谷底向东追踪至源区 ===')


def trace(c_start, r_start, direction, steps, window=60):
    path = [(r_start, c_start)]
    c = c_start
    for r in range(r_start, -1 if direction < 0 else ny, direction):
        c0, c1 = max(0, c - window), min(nx, c + window + 1)
        seg = Af[r, c0:c1]
        if not np.isfinite(seg).any():
            continue
        c = int(np.nanargmin(seg)) + c0
        path.append((r, c))
        if len(path) >= steps:
            break
    return path


# 口岸向北追踪
p_up = trace(pc, pr, -1, 400)
print('口岸向北追踪 %d 行, 终点 row%d col%d (%.4fE %.4fN) %.0f m'
      % (len(p_up), p_up[-1][0], p_up[-1][1], *ll(*p_up[-1]), Z[p_up[-1]]))
# 源区向南追踪
s_down = trace(sc, sr, 1, 400)
print('源区向南追踪 %d 行, 终点 row%d col%d (%.4fE %.4fN) %.0f m'
      % (len(s_down), s_down[-1][0], s_down[-1][1], *ll(*s_down[-1]), Z[s_down[-1]]))

print()
print('=== 直接检查源区->口岸之间地形 (取每行/每列最低, 看是否为同一河谷) ===')
# 沿两点连线的谷底剖面
N = 24
print('  t    col  row   经度      纬度     谷底高程')
for i in range(N + 1):
    t = i / N
    r = int(sr + (pr - sr) * t); c = int(sc + (pc - sc) * t)
    r0, r1 = max(0, r - 12), min(ny, r + 13)
    c0, c1 = max(0, c - 12), min(nx, c + 13)
    blk = Af[r0:r1, c0:c1]
    v = np.nanmin(blk) if np.isfinite(blk).any() else np.nan
    lo, la = ll(r, c)
    print('  %.2f %5d %5d  %.5f  %.5f   %6.0f' % (t, c, r, lo, la, v))
