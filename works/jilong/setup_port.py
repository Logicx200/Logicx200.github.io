# -*- coding: utf-8 -*-
"""
以用户提供的核心受灾点(85.3775108,28.2785535)为基准：
1) 核对其 DEM 高程
2) 沿谷底向上游追踪真实沟道
3) 输出源区->口岸的沟道几何，供建模使用
"""
import numpy as np
from osgeo import osr
from PIL import Image, ImageDraw

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
valid = A > -1000
E0, N1, RES = 322000.0, 3161000.0, 30.0
Af = np.where(valid, A, np.nan)

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ctU = osr.CoordinateTransformation(s1, s2)
ctL = osr.CoordinateTransformation(s2, s1)


def rc(lon, lat):
    x, y, _ = ctU.TransformPoint(float(lon), float(lat))
    return int((x - E0) / RES), int((N1 - y) / RES), x, y


def ll(r, c):
    lon, lat, _ = ctL.TransformPoint(float(E0 + c * RES), float(N1 - r * RES))
    return lon, lat


# ===== 1) 核心受灾点 =====
PD_LON, PD_LAT = 85.3775108377208, 28.2785535398864
pc, pr, px, py = rc(PD_LON, PD_LAT)
print('=== 核心受灾点 ===')
print('  经纬度 %.7f E, %.7f N' % (PD_LON, PD_LAT))
print('  UTM45N E=%.0f N=%.0f' % (px, py))
print('  DEM 网格 col=%d row=%d' % (pc, pr))
# 邻域最低点（河谷底）
r0, r1 = max(0, pr - 15), min(ny, pr + 16)
c0, c1 = max(0, pc - 15), min(nx, pc + 16)
blk = Af[r0:r1, c0:c1]
k = np.unravel_index(np.nanargmin(blk), blk.shape)
vr, vc = r0 + k[0], c0 + k[1]
print('  该点高程        %.0f m' % A[pr, pc])
lon_v, lat_v = ll(vr, vc)
print('  邻域河谷底(15格内) %.0f m @ col=%d row=%d  (%.5fE %.5fN)'
      % (A[vr, vc], vc, vr, lon_v, lat_v))
print('  受灾点高于谷底 %.0f m' % (A[pr, pc] - A[vr, vc]))

# ===== 2) 从河谷底向上游追踪 =====
print()
print('=== 沟道追踪（谷底 -> 上游）===')
path = [(vr, vc)]
window = 100
for r in range(vr - 1, -1, -1):
    if not valid[r].any():
        continue
    c_prev = path[-1][1]
    a, b = max(0, c_prev - window), min(nx, c_prev + window + 1)
    seg = Af[r, a:b]
    if not np.isfinite(seg).any():
        continue
    c = int(np.nanargmin(seg)) + a
    path.append((r, c))
path = path[::-1]
v = np.array([A[r, c] for r, c in path])
print('  长度 %.1f km, 高程 %.0f -> %.0f m, 落差 %.0f m'
      % (len(path) * RES / 1000, v[0], v[-1], v[0] - v[-1]))
print('  逆坡段 %d / %d' % ((np.diff(v) > 20).sum(), len(v) - 1))
np.save(W + r'\channel_final.npy', np.array(path))

print()
print('=== 沟道剖面 ===')
for k2 in range(0, len(path), max(1, len(path) // 28)):
    r, c = path[k2]
    d = np.hypot((c - vc) * RES, (r - vr) * RES) / 1000
    print('  距口岸 %5.1f km  高程 %5.0f m  (%.4fE %.4fN)'
          % (d, A[r, c], *ll(r, c)))

# ===== 3) 源区候选在沟道上的对应点 =====
SRC_LON, SRC_LAT = 85.2953, 28.4997
sc, sr, _, _ = rc(SRC_LON, SRC_LAT)
print()
print('=== 源区候选 A ===')
print('  col=%d row=%d 高程=%.0f m' % (sc, sr, A[sr, sc]))
same = min(path, key=lambda p: abs(p[0] - sr))
dhoriz = np.hypot((same[1] - sc) * RES, 0) / 1000
print('  同纬度沟道点 row=%d col=%d 高程=%.0f m' % (same[0], same[1], A[same[0], same[1]]))
print('  支沟水平距离 %.2f km, 落差 %.0f m, 平均坡度 %.1f%%'
      % (dhoriz, A[sr, sc] - A[same[0], same[1]],
         100 * (A[sr, sc] - A[same[0], same[1]]) / max(dhoriz * 1000, 1)))

# ===== 4) 出图 =====
def hillshade(z, res, az=315.0, alt=45.0):
    gy, gx = np.gradient(z, res, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr = np.radians(360.0 - az + 90.0)
    altr = np.radians(alt)
    return np.clip(np.sin(altr) * np.cos(slope) +
                   np.cos(altr) * np.sin(slope) * np.cos(azr - aspect), 0, 1)


hs = hillshade(Af, RES)
lo, hi = np.nanpercentile(Af, [2, 98])
el = np.clip((Af - lo) / max(hi - lo, 1), 0, 1)
rgb = np.stack([0.4 + 0.55 * el] * 3, -1) * (0.45 + 0.55 * hs)[:, :, None]
rgb[~np.isfinite(Af)] = [0.1, 0.1, 0.35]
img = Image.fromarray((np.clip(np.nan_to_num(rgb), 0, 1) * 255).astype(np.uint8))
dr = ImageDraw.Draw(img)
for i in range(len(path) - 1):
    r1_, c1_ = path[i]; r2_, c2_ = path[i + 1]
    dr.line([c1_, r1_, c2_, r2_], fill=(255, 60, 60), width=3)
for (cc, rr, col, tx) in [(vc, vr, (0, 255, 255), 'PORT'),
                          (sc, sr, (255, 255, 0), 'SRC cand')]:
    dr.ellipse([cc - 16, rr - 16, cc + 16, rr + 16], outline=col, width=4)
    dr.text((cc + 20, rr - 20), tx, fill=col)
img.resize((1100, 1100), Image.LANCZOS).save(W + r'\channel_map.jpg', quality=90)
print()
print('-> channel_map.jpg  (红线=追踪沟道, 黄=源区候选, 青=核心受灾点)')
