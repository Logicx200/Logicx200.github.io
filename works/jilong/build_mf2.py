# -*- coding: utf-8 -*-
"""
重建 MassFlow 输入，采用各向异性网格以适应 10 万格上限。
横向(dx)细分以分辨河谷，纵向(dy)放大以覆盖 35km 流程。
"""
import os
import json
import numpy as np
from osgeo import gdal, osr

W = r'F:\DeepSeek工作区\jilong'
OUT = os.path.join(W, 'mf_run2')
os.makedirs(OUT, exist_ok=True)

# ---- 网格设计 ----
DX = 30.0            # 横向 30 m（分辨 170 m 宽河谷）
DY = 300.0           # 纵向 300 m
E0, E1 = 322900.0, 346000.0
N0, N1 = 3126000.0, 3161000.0
NX = int(round((E1 - E0) / DX))
NY = int(round((N1 - N0) / DY))
print('网格 %d x %d = %d 格  (上限约 100000)' % (NX, NY, NX * NY))
print('覆盖 %.1f x %.1f km,  dx=%.0f m  dy=%.0f m, 长宽比 1:%.1f'
      % (NX * DX / 1000, NY * DY / 1000, DX, DY, DY / DX))
assert NX * NY < 100000, '超限'

# ---- 重采样 DEM 到该网格 ----
src = os.path.join(W, 'dem30_final.tif')
mem = gdal.Warp('', src, dstSRS='EPSG:32645',
                outputBounds=[E0, N0, E1, N1], xRes=DX, yRes=DY,
                resampleAlg='bilinear', format='MEM',
                srcNodata=-9999, dstNodata=-9999)
Z = mem.GetRasterBand(1).ReadAsArray().astype('f8')
print('重采样后 Z shape =', Z.shape)
valid = Z > -1000
if not valid.all():
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    Z[~valid] = Z[tuple(idx[:, ~valid])]
    print('  填补空洞 %d 格' % (~valid).sum())
# 保证行序: row0 = 北
print('  Z 范围 %.0f .. %.0f m' % (Z.min(), Z.max()))

# ---- 源区：直接在前一个工程定义的位置上重建（冰崩体 0.76 km2 / 70e6 m3）----
s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s1, s2)
SRC_LON, SRC_LAT = 85.2953, 28.4997
sx, sy, _ = ct.TransformPoint(SRC_LON, SRC_LAT)
sc = (sx - E0) / DX
sr = (N1 - sy) / DY
print()
print('源区 中心 col=%.1f row=%.1f  (UTM %.0f %.0f)' % (sc, sr, sx, sy))

# 椭圆高斯厚度场: 沿流向 780 m, 横向 980 m
LEN_M, WID_M = 780.0, 980.0
VOL_T = 70e6
pc = (340873.0 - E0) / DX      # 口岸/受灾点
pr = (N1 - 3129127.0) / DY
theta = np.arctan2(pr - sr, pc - sc)
yy, xx = np.mgrid[0:NY, 0:NX]
px = (xx - sc) * DX
py = (yy - sr) * DY
u = px * np.cos(theta) + py * np.sin(theta)
v = -px * np.sin(theta) + py * np.cos(theta)
a, b = LEN_M / 2.0, WID_M / 2.0
inside = (np.abs(u) <= a) & (np.abs(v) <= b)
prof = np.clip(1.0 - (u / a) ** 2, 0, None) ** 0.5
lat = np.exp(-(v / (b * 0.55)) ** 2)
H = np.where(inside, prof * lat, 0.0)
area = (H > 0).sum() * DX * DY
k = VOL_T / (H.sum() * DX * DY)
H = H * k
print('源区: 面积 %.3f km2 (目标 0.76), 体积 %.1f e6 m3 (目标 70), 最大厚 %.1f m, 平均厚 %.1f m'
      % (area / 1e6, H.sum() * DX * DY / 1e6, H.max(), H[H > 0].mean()))

# ---- 写 ASCII ----
def write_ascii(path, arr, cs, nodata):
    with open(path, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     %.6f\n' % E0)
        f.write('yllcorner     %.6f\n' % N0)
        f.write('cellsize      %.6f\n' % cs)
        f.write('NODATA_value  %.1f\n' % nodata)
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % x for x in arr[r]) + '\n')


# 头里的 cellsize 用 min(DX,DY)，真实间距由 *create,grid 决定
write_ascii(os.path.join(OUT, 'z.txt'), Z, min(DX, DY), -9999.0)
write_ascii(os.path.join(OUT, 'h.txt'), H, min(DX, DY), 0.0)
print('已写 z.txt / h.txt')

inp = """!计算区块数
*nregions,1
!分析类型 1:单层单相流
*type,1
*erosion,0
*density,0
*grav_inertia,0
!计算维度 2:二维
*ndim,2
*mbc,0
*remesh,0
*mpi,0
*omp,8
*limiter,1
*q1_flag,1
*solver,1
!各向异性网格: dx=%.1f m(横) dy=%.1f m(纵)
*create,grid,input,1,%d,%d,%.6f,%.6f,%.1f,%.1f
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.15,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,400,0.01,0.25
*output,1,tecplot,1,1,1,20
""" % (DX, DY, NX, NY, E0, N0, DX, DY)
with open(os.path.join(OUT, 'input.txt'), 'w', encoding='gbk') as f:
    f.write(inp)

import shutil
for fn in ('massflow.exe', 'solver.dll'):
    shutil.copy2(os.path.join(r'D:\MassFlow\massflow\Bin\massflow', fn), os.path.join(OUT, fn))

json.dump(dict(DX=DX, DY=DY, NX=NX, NY=NY, E0=E0, N0=N0, N1=N1,
               src_col=float(sc), src_row=float(sr), vol_e6=float(H.sum() * DX * DY / 1e6),
               area_km2=float(area / 1e6), hmax=float(H.max())),
          open(os.path.join(OUT, 'meta.json'), 'w'), indent=2)
np.save(os.path.join(OUT, 'Z.npy'), Z)
np.save(os.path.join(OUT, 'H.npy'), H)
print('完成 ->', OUT)
