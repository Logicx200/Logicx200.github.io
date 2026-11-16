# -*- coding: utf-8 -*-
"""
地形晕渲（真晕渲）与剖面，用于目视确认河谷走向。
输出三张图：全域晕渲、口岸周边、源区候选区。
"""
import numpy as np
from osgeo import osr
from PIL import Image

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
E0, N1, RES = 322000, 3161000, 30
valid = A > -1000
Af = np.where(valid, A, np.nan)

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s2, s1)


def ll(r, c):
    lon, lat, _ = ct.TransformPoint(float(E0 + c * RES), float(N1 - r * RES))
    return lon, lat


# 真晕渲：光照方位 315 度, 高度角 45 度
def hillshade(z, res, az=315.0, alt=45.0):
    gy, gx = np.gradient(z, res, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr = np.radians(360.0 - az + 90.0)
    altr = np.radians(alt)
    shaded = np.sin(altr) * np.cos(slope) + np.cos(altr) * np.sin(slope) * np.cos(azr - aspect)
    return np.clip(shaded, 0, 1)


def save(z, out, scale=1.0, marks=None, title=''):
    hs = hillshade(z, RES)
    lo, hi = np.nanpercentile(z, [2, 98])
    elev = np.clip((z - lo) / max(hi - lo, 1), 0, 1)
    # 晕渲 + 高程色彩
    rgb = np.zeros(z.shape + (3,), np.float32)
    rgb[:, :, 0] = 0.35 + 0.55 * elev
    rgb[:, :, 1] = 0.35 + 0.55 * elev
    rgb[:, :, 2] = 0.35 + 0.55 * elev
    rgb *= (0.45 + 0.55 * hs)[:, :, None]
    rgb[~np.isfinite(z)] = [0.1, 0.1, 0.4]
    img = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(img)
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    im.save(out, quality=90)
    print('  -> %s  (%dx%d)' % (out, im.width, im.height))


# 1) 全域
save(Af, W + r'\terrain_full.jpg', scale=0.75)
print('全域: 左上=%.4fE %.4fN  右下=%.4fE %.4fN' % (
    *ll(0, 0)[:2][::-1], *ll(ny - 1, nx - 1)[:2][::-1]))

# 2) 口岸周边 (row 850-1200, col 400-900)
sub = Af[850:1200, 400:900]
save(sub, W + r'\terrain_port.jpg', scale=2.0)
print('口岸区: col400-900 row850-1200 -> %.4f-%.4f E, %.4f-%.4f N' % (
    ll(850, 400)[0], ll(850, 900)[0], ll(1200, 400)[1], ll(850, 400)[1]))

# 3) 源区候选 (row 0-600, col 0-700)
sub = Af[0:600, 0:700]
save(sub, W + r'\terrain_src.jpg', scale=1.5)
print('源区西: col0-700 row0-600 -> %.4f-%.4f E, %.4f-%.4f N' % (
    ll(0, 0)[0], ll(0, 700)[0], ll(600, 0)[1], ll(0, 0)[1]))

# 4) 源区候选 东北 (row 0-600, col 600-1200)
sub = Af[0:600, 600:1200]
save(sub, W + r'\terrain_srcE.jpg', scale=1.5)
print('源区东: col600-1200 row0-600 -> %.4f-%.4f E, %.4f-%.4f N' % (
    ll(0, 600)[0], ll(0, 1200)[0], ll(600, 600)[1], ll(0, 600)[1]))
