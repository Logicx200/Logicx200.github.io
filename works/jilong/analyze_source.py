# -*- coding: utf-8 -*-
"""判读冰崩源区：高海拔连通块 + 与主沟道的关系"""
import numpy as np
from osgeo import osr
from scipy import ndimage

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy')
ny, nx = A.shape
E0, N1, RES = 322000, 3161000, 30

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s2, s1)


def ll(r, c):
    lon, lat, _ = ct.TransformPoint(float(E0 + c * RES), float(N1 - r * RES))
    return lon, lat


# 主沟道参考点 (row, col)，由口岸向上游追踪得到
ch = [(1031, 602), (911, 511), (791, 564), (711, 504), (631, 425),
      (551, 305), (471, 237), (391, 176), (311, 140), (231, 119),
      (151, 114), (71, 160), (31, 193)]
chr = np.array([p[0] for p in ch]); chc = np.array([p[1] for p in ch])

print('=== 主沟道控制点 ===')
for r, c in ch:
    lon, lat = ll(r, c)
    print('  row%4d col%4d  %.4fE %.4fN  %5.0f m' % (r, c, lon, lat, A[r, c]))

print()
for thr in (4500, 4800, 5000, 5200):
    hi = A > thr
    lab, n = ndimage.label(hi)
    sizes = ndimage.sum(hi, lab, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    print('=== 阈值 >%d m : %d 块, 合计 %d 像元 (%.0f km2) ===' % (
        thr, n, hi.sum(), hi.sum() * 900 / 1e6))
    for k in order[:8]:
        m = (lab == k + 1)
        rr, cc = np.where(m)
        pk = A[rr, cc].max()
        lon, lat = ll(int(rr.mean()), int(cc.mean()))
        d = min(np.hypot((rr - r0) * RES, (cc - c0) * RES).min()
                for r0, c0 in ch)
        print('   块%3d %7d 像元 %6.1f km2  最高%5.0f m  中心 %.4fE %.4fN  距主沟 %.2f km' % (
            k + 1, sizes[k], sizes[k] * 900 / 1e6, pk, lon, lat, d / 1000))
    print()
