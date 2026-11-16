# -*- coding: utf-8 -*-
"""
用修正后的坐标重建 MassFlow 模型。

正确流路（已用 DEM 逐行谷底追踪验证，全程单调下降）：
  冰崩源区 85.51225662,28.29062626 -> 谷底 3634 m
  堰塞湖   85.48521996,28.33256414 -> 谷底 2816 m   (6.0 km)
  吉隆口岸 85.37793159,28.27947783 -> 谷底 1737 m   (11.2 km)
  合计落差 1897 m，沿程约 17.2 km

网格：各向异性，横向 30 m（分辨河谷），纵向 150 m（沿流程）
"""
import os
import json
import shutil
import numpy as np
from osgeo import gdal, osr

W = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(W, 'mf_real')
os.makedirs(OUT, exist_ok=True)

DX = 30.0        # 东西向
DY = 150.0       # 南北向
E0, E1 = 338000.0, 357000.0     # 19 km
N0, N1 = 3125500.0, 3139000.0   # 13.5 km
NX = int(round((E1 - E0) / DX))
NY = int(round((N1 - N0) / DY))
print('网格 %d x %d = %d 格 (上限 ~100000)' % (NX, NY, NX * NY))
print('覆盖 %.1f x %.1f km   dx=%.0f m  dy=%.0f m' % (NX * DX / 1000, NY * DY / 1000, DX, DY))
assert NX * NY < 99000, '超限'

# --- 从原始 DEM 重采样 ---
src = r'D:\下载 (1)\2026年8月26日日喀则市吉隆县泥石流灾害区DEM数据\DEM.tif'
mem = gdal.Warp('', src, dstSRS='EPSG:32645',
                outputBounds=[E0, N0, E1, N1], xRes=DX, yRes=DY,
                resampleAlg='bilinear', format='MEM',
                srcNodata=-32767, dstNodata=-9999)
Z = mem.GetRasterBand(1).ReadAsArray().astype('f8')
print('Z shape', Z.shape, ' 范围 %.0f..%.0f m' % (Z.min(), Z.max()))
valid = Z > -1000
if not valid.all():
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    Z[~valid] = Z[tuple(idx[:, ~valid])]
    print('  填补空洞 %d 格' % (~valid).sum())

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s1, s2)


def rc(lon, lat):
    x, y, _ = ct.TransformPoint(float(lon), float(lat))
    return (x - E0) / DX, (N1 - y) / DY, x, y


SRC_LON, SRC_LAT = 85.51225662, 28.29062626
LAKE_LON, LAKE_LAT = 85.48521996, 28.33256414
PORT_LON, PORT_LAT = 85.37793159, 28.27947783
sc, sr, sx, sy = rc(SRC_LON, SRC_LAT)
lc, lr, lx, ly = rc(LAKE_LON, LAKE_LAT)
pc, pr, px, py = rc(PORT_LON, PORT_LAT)
print()
print('源区 col=%.1f row=%.1f  (%.0f %.0f)' % (sc, sr, sx, sy))
print('堰塞湖 col=%.1f row=%.1f' % (lc, lr))
print('口岸 col=%.1f row=%.1f' % (pc, pr))
print('源区在地面高程 %.0f m' % Z[int(sr), int(sc)])

# --- 冰崩体：0.76 km2 / 70e6 m3，置于源区上游坡面 ---
# 沿流向为 源区->堰塞湖 方向
ang = np.arctan2(lr - sr, lc - sc)
LEN_M, WID_M, VOL_T = 780.0, 980.0, 70e6
yy, xx = np.mgrid[0:NY, 0:NX]
pxx = (xx - sc) * DX
pyy = (yy - sr) * DY
u = pxx * np.cos(ang) + pyy * np.sin(ang)
v = -pxx * np.sin(ang) + pyy * np.cos(ang)
a, b = LEN_M / 2.0, WID_M / 2.0
inside = (np.abs(u) <= a) & (np.abs(v) <= b)
H = np.where(inside, np.clip(1 - (u / a) ** 2, 0, None) ** 0.5 * np.exp(-(v / (b * 0.55)) ** 2), 0.0)
area = (H > 0).sum() * DX * DY
H = H * (VOL_T / (H.sum() * DX * DY))
print()
print('冰崩体: 面积 %.3f km2 (目标0.76)  体积 %.1f e6 m3 (目标70)  最大厚 %.1f m  平均厚 %.1f m'
      % (area / 1e6, H.sum() * DX * DY / 1e6, H.max(), H[H > 0].mean()))


def write_ascii(path, arr, nodata):
    with open(path, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     %.6f\n' % E0)
        f.write('yllcorner     %.6f\n' % N0)
        f.write('cellsize      %.6f\n' % min(DX, DY))
        f.write('NODATA_value  %.1f\n' % nodata)
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % x for x in arr[r]) + '\n')


write_ascii(os.path.join(OUT, 'z.txt'), Z, -9999.0)
write_ascii(os.path.join(OUT, 'h.txt'), H, 0.0)

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
!各向异性网格 dx=%.1f(东西) dy=%.1f(南北)
*create,grid,input,1,%d,%d,%.6f,%.6f,%.1f,%.1f
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.05,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,400,0.01,0.25
*output,1,tecplot,1,1,1,20
""" % (DX, DY, NX, NY, E0, N0, DX, DY)
open(os.path.join(OUT, 'input.txt'), 'w', encoding='gbk').write(inp)
for fn in ('massflow.exe', 'solver.dll'):
    shutil.copy2(os.path.join(r'D:\MassFlow\massflow\Bin\massflow', fn), os.path.join(OUT, fn))

json.dump(dict(DX=DX, DY=DY, NX=NX, NY=NY, E0=E0, N0=N0, N1=N1, E1=E1,
               src_col=float(sc), src_row=float(sr),
               lake_col=float(lc), lake_row=float(lr),
               port_col=float(pc), port_row=float(pr),
               vol_e6=float(H.sum() * DX * DY / 1e6), area_km2=float(area / 1e6),
               hmax=float(H.max())),
          open(os.path.join(OUT, 'meta.json'), 'w'), indent=2)
np.save(os.path.join(OUT, 'Z.npy'), Z)
np.save(os.path.join(OUT, 'H.npy'), H)
print()
print('已写出 ->', OUT)
