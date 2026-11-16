# -*- coding: utf-8 -*-
"""
(A) 收敛性检验：把横向格距从 20 m 粗化到 40 m（纵向同步粗化），
    比较前缘抵达时间。若差异很小，说明 20 m 已收敛。
(B) 高精度加固：收紧域 + 15 m x 110 m，换取横向再细化 25%。
"""
import os
import json
import shutil
import numpy as np
from osgeo import gdal, osr

B = r'F:\DeepSeek工作区\jilong'
SRCDEM = r'D:\下载 (1)\2026年8月26日日喀则市吉隆县泥石流灾害区DEM数据\DEM.tif'
s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s1, s2)
SRC_LONLAT = (85.51225662, 28.29062626)
LAKE_LONLAT = (85.48521996, 28.33256414)
PORT_LONLAT = (85.37793159, 28.27947783)


def build(tag, DX, DY, E0, E1, N0, N1, T=1200, out_int=20, omp=4):
    d = os.path.join(B, tag)
    os.makedirs(d, exist_ok=True)
    NX = int(round((E1 - E0) / DX))
    NY = int(round((N1 - N0) / DY))
    nc = NX * NY
    print('%-12s dx=%.0f dy=%.0f  %dx%d = %d 格  域 %.1f x %.1f km'
          % (tag, DX, DY, NX, NY, nc, NX * DX / 1000, NY * DY / 1000))
    if nc >= 99900:
        print('   超限，跳过'); return None
    mem = gdal.Warp('', SRCDEM, dstSRS='EPSG:32645', outputBounds=[E0, N0, E1, N1],
                    xRes=DX, yRes=DY, resampleAlg='bilinear', format='MEM',
                    srcNodata=-32767, dstNodata=-9999)
    Z = mem.GetRasterBand(1).ReadAsArray().astype('f8')
    v = Z > -1000
    if not v.all():
        from scipy import ndimage
        idx = ndimage.distance_transform_edt(~v, return_distances=False, return_indices=True)
        Z[~v] = Z[tuple(idx[:, ~v])]

    def rc(lon, lat):
        x, y, _ = ct.TransformPoint(float(lon), float(lat))
        return (x - E0) / DX, (N1 - y) / DY
    sc, sr = rc(*SRC_LONLAT)
    lc, lr = rc(*LAKE_LONLAT)
    pc, pr = rc(*PORT_LONLAT)
    if not (5 < sc < NX - 5 and 5 < sr < NY - 5 and 5 < pc < NX - 5):
        print('   锚点越界: src(%.0f,%.0f) port(%.0f,%.0f)' % (sc, sr, pc, pr)); return None

    ang = np.arctan2(lr - sr, lc - sc)
    L, Wd, VOL = 780.0, 980.0, 70e6
    yy, xx = np.mgrid[0:NY, 0:NX]
    u = (xx - sc) * DX * np.cos(ang) + (yy - sr) * DY * np.sin(ang)
    vv = -(xx - sc) * DX * np.sin(ang) + (yy - sr) * DY * np.cos(ang)
    a, b = L / 2, Wd / 2
    H = np.where((np.abs(u) <= a) & (np.abs(vv) <= b),
                 np.clip(1 - (u / a) ** 2, 0, None) ** 0.5 * np.exp(-(vv / (b * 0.55)) ** 2), 0.0)
    H = H * (VOL / (H.sum() * DX * DY))

    def wr(p, arr, nodata):
        with open(p, 'w', encoding='ascii') as f:
            f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
            f.write('xllcorner     %.6f\nyllcorner     %.6f\n' % (E0, N0))
            f.write('cellsize      %.6f\nNODATA_value  %.1f\n' % (min(DX, DY), nodata))
            for r in range(arr.shape[0]):
                f.write(' '.join('%.3f' % x for x in arr[r]) + '\n')
    wr(os.path.join(d, 'z.txt'), Z, -9999.0)
    wr(os.path.join(d, 'h.txt'), H, 0.0)
    inp = """*nregions,1
*type,1
*erosion,0
*density,0
*grav_inertia,0
*ndim,2
*mbc,0
*remesh,0
*mpi,0
*omp,%d
*limiter,1
*q1_flag,1
*solver,1
*create,grid,input,1,%d,%d,%.6f,%.6f,%.1f,%.1f
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.005,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,%d,0.01,0.25
*output,1,tecplot,1,1,1,%d
""" % (omp, NX, NY, E0, N0, DX, DY, T, out_int)
    open(os.path.join(d, 'input.txt'), 'w', encoding='gbk').write(inp)
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(r'D:\MassFlow\massflow\Bin\massflow', f), os.path.join(d, f))
    for f in ('output1_region1.plt', 'stdout.log', 'cmd.txt', '_status.txt'):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    json.dump(dict(DX=DX, DY=DY, NX=NX, NY=NY, E0=E0, N0=N0, N1=N1, E1=E1,
                   src_col=float(sc), src_row=float(sr), lake_col=float(lc), lake_row=float(lr),
                   port_col=float(pc), port_row=float(pr)), open(os.path.join(d, 'meta.json'), 'w'))
    np.save(os.path.join(d, 'Z.npy'), Z)
    np.save(os.path.join(d, 'H.npy'), H)
    return d


print('=== (A) 收敛性检验：粗化网格 ===')
# 与 mf_hi 同域，横向 40 m（纵向同步粗化到 280 m）
build('cv_coarse40', 40.0, 280.0, 338000.0, 356000.0, 3125500.0, 3139000.0)
# 中间档 30 m
build('cv_mid30', 30.0, 200.0, 338000.0, 356000.0, 3125500.0, 3139000.0)

print()
print('=== (B) 收紧域 + 15 m 横向 ===')
# 锚点 UTM: 源区 354107, 堰塞湖 351513, 口岸 340916
# 收紧为 E 339200..355200 (16.0 km), N 3126000..3138200 (12.2 km)
# 15m x 135m -> 1067 x 90 = 96,030 格（横向优于 20m，留余量）
build('hi15', 15.0, 135.0, 339200.0, 355200.0, 3126000.0, 3138200.0)
