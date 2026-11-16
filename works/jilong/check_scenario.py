# -*- coding: utf-8 -*-
"""
绘制源区候选、口岸、运动路径叠加图，核实 22 km / 3500 m 落差约束。
"""
import numpy as np
from osgeo import osr
from PIL import Image, ImageDraw

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
E0, N1, RES = 322000, 3161000, 30
valid = A > -1000
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


def hillshade(z, res, az=315.0, alt=45.0):
    gy, gx = np.gradient(z, res, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr = np.radians(360.0 - az + 90.0)
    altr = np.radians(alt)
    return np.clip(np.sin(altr) * np.cos(slope) +
                   np.cos(altr) * np.sin(slope) * np.cos(azr - aspect), 0, 1)


# 关键点
SRC = (85.2953, 28.4997)      # 源区候选A
PORT = (85.3767, 28.2871)     # 吉隆口岸(热索桥)
sc, sr = rc(*SRC); pc, pr = rc(*PORT)
print('源区候选A: col=%d row=%d 高程=%.0f m' % (sc, sr, A[sr, sc]))
print('吉隆口岸 : col=%d row=%d 高程=%.0f m' % (pc, pr, A[pr, pc]))
dist = np.hypot((pc - sc) * RES, (pr - sr) * RES) / 1000
print('源区->口岸 直线距离 %.1f km, 落差 %.0f m' % (dist, A[sr, sc] - A[pr, pc]))

# 输出剖面（沿直线，取 ±200m 内最低高程近似沟道）
print()
print('=== 源区->口岸 廊道剖面 ===')
N = 30
for i in range(N + 1):
    t = i / N
    r = int(sr + (pr - sr) * t); c = int(sc + (pc - sc) * t)
    r0, r1 = max(0, r - 7), min(ny, r + 8)
    c0, c1 = max(0, c - 7), min(nx, c + 8)
    blk = A[r0:r1, c0:c1]; bv = valid[r0:r1, c0:c1]
    if bv.any():
        lo = np.nanmin(blk[bv])
        d = np.hypot((c - sc) * RES, (r - sr) * RES) / 1000
        print('  %5.1f km  谷底 %5.0f m' % (d, lo))

# 出图
hs = hillshade(Af, RES)
lo, hi = np.nanpercentile(Af, [2, 98])
elev = np.clip((Af - lo) / max(hi - lo, 1), 0, 1)
rgb = np.stack([0.4 + 0.55 * elev] * 3, -1) * (0.45 + 0.55 * hs)[:, :, None]
rgb[~np.isfinite(Af)] = [0.1, 0.1, 0.35]
img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
dr = ImageDraw.Draw(img)


def mark(c, r, col, txt, rad=22):
    dr.ellipse([c - rad, r - rad, c + rad, r + rad], outline=col, width=5)
    dr.text((c + rad + 4, r - rad - 4), txt, fill=col)


mark(sc, sr, (255, 40, 40), 'SRC 5296m')
mark(pc, pr, (40, 200, 255), 'PORT 1802m')
dr.line([sc, sr, pc, pr], fill=(255, 230, 0), width=4)
img = img.resize((1100, 1100), Image.LANCZOS)
img.save(W + r'\scenario_check.jpg', quality=90)
print()
print('-> scenario_check.jpg  红线=SRC 蓝线=PORT 黄线=直线路径')
