# -*- coding: utf-8 -*-
"""
高精度重建：在 10 万格上限内最大化分辨率。
原网格 30m x 150m = 56,970 格（域 19 x 13.5 km）
新网格 20m x 100m，域收至 18 x 13.5 km -> 900 x 135 = 121,500 超限
故取 20m x 120m -> 900 x 113 = 101,700 仍超
改取 22m x 130m -> 818 x 104 = 85,072
最终取 20m x 140m -> 900 x 97 = 87,300 格
  -> 横向由 30m 提到 20m（+50% 精度）
  -> 纵向由 150m 提到 140m
"""
import os
import json
import shutil
import numpy as np
from osgeo import gdal, osr

B = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(B, 'mf_hi')
os.makedirs(OUT, exist_ok=True)

DX, DY = 20.0, 140.0
E0, E1 = 338000.0, 356000.0
N0, N1 = 3125500.0, 3139000.0
NX = int(round((E1 - E0) / DX))
NY = int(round((N1 - N0) / DY))
print('新网格 %d x %d = %d 格  (上限 ~100000)' % (NX, NY, NX * NY))
print('覆盖 %.1f x %.1f km   dx=%.0f m  dy=%.0f m' % (NX * DX / 1000, NY * DY / 1000, DX, DY))
assert NX * NY < 99900, '超限'

src = r'D:\下载 (1)\2026年8月26日日喀则市吉隆县泥石流灾害区DEM数据\DEM.tif'
mem = gdal.Warp('', src, dstSRS='EPSG:32645',
                outputBounds=[E0, N0, E1, N1], xRes=DX, yRes=DY,
                resampleAlg='bilinear', format='MEM',
                srcNodata=-32767, dstNodata=-9999)
Z = mem.GetRasterBand(1).ReadAsArray().astype('f8')
print('Z', Z.shape, '%.0f..%.0f m' % (Z.min(), Z.max()))
valid = Z > -1000
if not valid.all():
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    Z[~valid] = Z[tuple(idx[:, ~valid])]
    print('  填补 %d' % (~valid).sum())

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s1, s2)


def rc(lon, lat):
    x, y, _ = ct.TransformPoint(float(lon), float(lat))
    return (x - E0) / DX, (N1 - y) / DY


SRC = rc(85.51225662, 28.29062626)
LAKE = rc(85.48521996, 28.33256414)
PORT = rc(85.37793159, 28.27947783)
sc, sr = SRC
lc, lr = LAKE
pc, pr = PORT
print()
print('源区 col=%.1f row=%.1f' % (sc, sr))
print('堰塞湖 col=%.1f row=%.1f' % (lc, lr))
print('口岸 col=%.1f row=%.1f' % (pc, pr))

ang = np.arctan2(lr - sr, lc - sc)
LEN_M, WID_M, VOL_T = 780.0, 980.0, 70e6
yy, xx = np.mgrid[0:NY, 0:NX]
u = (xx - sc) * DX * np.cos(ang) + (yy - sr) * DY * np.sin(ang)
v = -(xx - sc) * DX * np.sin(ang) + (yy - sr) * DY * np.cos(ang)
a, b = LEN_M / 2.0, WID_M / 2.0
H = np.where((np.abs(u) <= a) & (np.abs(v) <= b),
             np.clip(1 - (u / a) ** 2, 0, None) ** 0.5 * np.exp(-(v / (b * 0.55)) ** 2), 0.0)
area = (H > 0).sum() * DX * DY
H = H * (VOL_T / (H.sum() * DX * DY))
print()
print('冰崩体 面积 %.3f km2 (目标0.76)  体积 %.1f e6 m3  最大厚 %.1f m'
      % (area / 1e6, H.sum() * DX * DY / 1e6, H.max()))


def wr(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
        f.write('xllcorner     %.6f\nyllcorner     %.6f\n' % (E0, N0))
        f.write('cellsize      %.6f\nNODATA_value  %.1f\n' % (min(DX, DY), nodata))
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % x for x in arr[r]) + '\n')


wr(os.path.join(OUT, 'z.txt'), Z, -9999.0)
wr(os.path.join(OUT, 'h.txt'), H, 0.0)

inp = """!计算区块数
*nregions,1
*type,1
*erosion,0
*density,0
*grav_inertia,0
*ndim,2
*mbc,0
*remesh,0
*mpi,0
*omp,8
*limiter,1
*q1_flag,1
*solver,1
!高精度各向异性网格 dx=%.1f(东西) dy=%.1f(南北)
*create,grid,input,1,%d,%d,%.6f,%.6f,%.1f,%.1f
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.005,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,1200,0.01,0.25
*output,1,tecplot,1,1,1,10
""" % (DX, DY, NX, NY, E0, N0, DX, DY)
open(os.path.join(OUT, 'input.txt'), 'w', encoding='gbk').write(inp)
for fn in ('massflow.exe', 'solver.dll'):
    shutil.copy2(os.path.join(r'D:\MassFlow\massflow\Bin\massflow', fn), os.path.join(OUT, fn))
for f in ('output1_region1.plt', 'stdout.log', 'cmd.txt'):
    p = os.path.join(OUT, f)
    if os.path.exists(p):
        os.remove(p)

json.dump(dict(DX=DX, DY=DY, NX=NX, NY=NY, E0=E0, N0=N0, N1=N1, E1=E1,
               src_col=float(sc), src_row=float(sr),
               lake_col=float(lc), lake_row=float(lr),
               port_col=float(pc), port_row=float(pr),
               vol_e6=float(H.sum() * DX * DY / 1e6), area_km2=float(area / 1e6)),
          open(os.path.join(OUT, 'meta.json'), 'w'), indent=2)
np.save(os.path.join(OUT, 'Z.npy'), Z)
np.save(os.path.join(OUT, 'H.npy'), H)
print()
print('已写出 ->', OUT)
print('注: 相对原网格(30x150) 横向精度 +50%%, 总格数 %d' % (NX * NY))
