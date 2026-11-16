# -*- coding: utf-8 -*-
"""补黑瓦片 + 用模拟流路叠加验证影像与 DEM 的几何对齐"""
import os, math, io
import numpy as np
import requests
from PIL import Image, ImageDraw

try:
    import certifi; CA = certifi.where()
except Exception: CA = True

B = r'F:\DeepSeek工作区\jilong'
TD = os.path.join(B, 'sat_tiles')
Z = 16
E0, E1 = 338000.0, 356000.0
N0, N1 = 3125500.0, 3139000.0
OW, OH = 8192, 6144
TX0, TY0 = 48304, 27378
NTX, NTY = 35, 27
URL = ('https://server.arcgisonline.com/ArcGIS/rest/services/'
       'World_Imagery/MapServer/tile/%d/%%d/%%d' % Z)

s = requests.Session(); s.headers['User-Agent'] = 'Mozilla/5.0'

# ---- 1) 找出黑/缺瓦片 ----
bad = []
for jy in range(NTY):
    for jx in range(NTX):
        p = os.path.join(TD, '%d_%d.jpg' % (TX0 + jx, TY0 + jy))
        if not os.path.exists(p):
            bad.append((TX0 + jx, TY0 + jy)); continue
        try:
            a = np.asarray(Image.open(p).convert('RGB'))
        except Exception:
            bad.append((TX0 + jx, TY0 + jy)); continue
        if (a.sum(axis=2) < 12).mean() > 0.9:
            bad.append((TX0 + jx, TY0 + jy))
print('黑/缺瓦片 %d 个: %s' % (len(bad), bad[:12]))

# ---- 2) 用 z=15 父瓦片放大填补 ----
for (x, y) in bad:
    got = False
    for pz in (15, 14, 17):
        px_, py_ = x >> (Z - pz), y >> (Z - pz)
        k = 2 ** (Z - pz)
        u, v = x - (px_ << (Z - pz)), y - (py_ << (Z - pz))
        try:
            r = s.get(URL.replace('/%d/' % Z, '/%d/' % pz) % (py_, px_), timeout=30, verify=CA)
            if r.status_code != 200 or len(r.content) < 2000:
                continue
            im = Image.open(io.BytesIO(r.content)).convert('RGB')
            a = np.asarray(im)
            if (a.sum(axis=2) < 12).mean() > 0.9:
                continue
            cw = im.width // k
            im = im.crop((u * cw, v * cw, (u + 1) * cw, (v + 1) * cw)).resize((256, 256), Image.LANCZOS)
            im.save(os.path.join(TD, '%d_%d.jpg' % (x, y)), quality=92)
            got = True
            print('   填补 (%d,%d) <- z%d' % (x, y, pz))
            break
        except Exception as e:
            pass
    if not got:
        print('   仍失败 (%d,%d)' % (x, y))

# ---- 3) 重新拼接 + 重投影 ----
from osgeo import gdal, osr
osr.UseExceptions()
gdal.UseExceptions()

def utm_to_lonlat(pts):
    a = osr.SpatialReference(); a.ImportFromEPSG(32645)
    b = osr.SpatialReference(); b.ImportFromEPSG(4326)
    a.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    b.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(a, b)
    return [ct.TransformPoint(x, y)[:2] for x, y in pts]

def lonlat_to_merc(lon, lat):
    R = 6378137.0
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def merc_to_px(x, y):
    world = 2 * math.pi * 6378137.0
    res = world / (256 * (2 ** Z))
    return (x + world / 2) / res, (world / 2 - y) / res

corners = [(E0, N0), (E1, N0), (E1, N1), (E0, N1)]
ll = utm_to_lonlat(corners)
px = [merc_to_px(*lonlat_to_merc(lo, la)) for lo, la in ll]

canvas = Image.new('RGB', (NTX * 256, NTY * 256), (0, 0, 0))
for jy in range(NTY):
    for jx in range(NTX):
        p = os.path.join(TD, '%d_%d.jpg' % (TX0 + jx, TY0 + jy))
        if os.path.exists(p):
            canvas.paste(Image.open(p).convert('RGB'), (jx * 256, jy * 256))

pxmin = min(p[0] for p in px) - TX0 * 256
pxmax = max(p[0] for p in px) - TX0 * 256
pymin = min(p[1] for p in px) - TY0 * 256
pymax = max(p[1] for p in px) - TY0 * 256
cx0, cy0 = int(math.floor(pxmin)), int(math.floor(pymin))
cx1, cy1 = int(math.ceil(pxmax)), int(math.ceil(pymax))
sub = canvas.crop((cx0, cy0, cx1, cy1))
cw, ch = sub.size
world = 2 * math.pi * 6378137.0
res = world / (256 * (2 ** Z))
mx0 = (cx0 + TX0 * 256) * res - world / 2
mx1 = (cx1 + TX0 * 256) * res - world / 2
my1 = world / 2 - (cy0 + TY0 * 256) * res
my0 = world / 2 - (cy1 + TY0 * 256) * res

mp = os.path.join(B, 'sat_merc.jpg')
sub.save(mp, quality=92)
with open(os.path.join(B, 'sat_merc.jgw'), 'w') as f:
    f.write('%.10f\n0\n0\n%.10f\n%.10f\n%.10f\n'
            % ((mx1 - mx0) / cw, -(my1 - my0) / ch,
               mx0 + (mx1 - mx0) / cw / 2, my1 - (my1 - my0) / ch / 2))

out = os.path.join(B, 'sat_utm.jpg')
d = gdal.Warp(out, mp, options=gdal.WarpOptions(
    format='JPEG', dstSRS='EPSG:32645', srcSRS='EPSG:3857',
    outputBounds=[E0, N0, E1, N1], width=OW, height=OH,
    resampleAlg=gdal.GRA_Cubic, creationOptions=['QUALITY=92']))
d = None
print('重投影完成 %s' % out)

# ---- 4) 叠流路验证 ----
sat = Image.open(out).convert('RGB')

def to_px(E, N):
    return ((E - E0) / (E1 - E0) * OW, (N1 - N) / (N1 - N0) * OH)

nz = np.load(os.path.join(B, 'blender', 'flow_hr.npz'))
H = nz['H']; hNY, hNX = int(nz['hNY']), int(nz['hNX'])
TRf = float(nz['TR']); Ef = float(nz['E0']); Nf = float(nz['N1'])
wet = (H > 0.05).any(axis=0)
ys, xs = np.where(wet)
Ee = Ef + xs * TRf
Nn = Nf - ys * TRf
print('湿区像元 %d, E %.0f..%.0f  N %.0f..%.0f' % (ys.size, Ee.min(), Ee.max(), Nn.min(), Nn.max()))

ov = sat.copy()
dr = ImageDraw.Draw(ov)
for E, N in zip(Ee[::7], Nn[::7]):
    x, y = to_px(E, N)
    dr.point((x, y), fill=(255, 0, 255))
for E, N in zip(Ee[::7], Nn[::7]):
    x, y = to_px(E, N)
    dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 0, 255), width=3)

pts = [('SRC', 85.51225662, 28.29062626), ('LAKE', 85.48521996, 28.33256414),
       ('PORT', 85.37793159, 28.27947783)]
c4 = utm_to_lonlat([(E0, N0), (E1, N1)])
for nm, lo, la in pts:
    a = osr.SpatialReference(); a.ImportFromEPSG(4326)
    b = osr.SpatialReference(); b.ImportFromEPSG(32645)
    a.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    b.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(a, b)
    E, N = ct.TransformPoint(lo, la)[:2]
    x, y = to_px(E, N)
    dr.ellipse([x - 18, y - 18, x + 18, y + 18], outline=(0, 255, 255), width=6)
    print('%-5s UTM %.0f %.0f -> px %.0f %.0f' % (nm, E, N, x, y))

ov.resize((1500, 1125), Image.LANCZOS).save(os.path.join(B, 'sat_overlay_check.png'))
print('对齐检查图: sat_overlay_check.png')
