# -*- coding: utf-8 -*-
"""
自动识别冰崩源区候选。
依据（来自文献）：
  - 冰川 RGI60-15.04173，面积 3.13 km2
  - 冰崩体 0.76 km2 / 体积 >70e6 m3 / 平均厚约92 m
  - 蓝塘里壤峰北坡，与口岸(约1800m)落差约3500m -> 源区约 5000-5500 m
判据：高程 4500-6200 m、坡度适中(冰面而非岩壁)、汇入已追踪的主沟道。
"""
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


gy, gx = np.gradient(A, RES, RES)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))

# 主沟道控制点（自口岸向上游追踪）
ch = [(1031, 602), (911, 511), (791, 564), (711, 504), (631, 425),
      (551, 305), (471, 237), (391, 176), (311, 140), (231, 119),
      (151, 114), (71, 160), (31, 193)]
chr_ = np.array([p[0] for p in ch]); chc_ = np.array([p[1] for p in ch])

print('DEM %dx%d  高程 %.0f..%.0f m' % (nx, ny, A.min(), A.max()))
print('源区参考：文献给出冰川 3.13 km2，冰崩体 0.76 km2，与口岸落差约3500m')
print()

# 候选：高程带 + 坡度带
for elo, ehi, slo, shi in [(4800, 6200, 0, 25), (4800, 6200, 0, 35),
                           (4500, 6200, 0, 30), (5000, 6200, 0, 30)]:
    m = (A >= elo) & (A <= ehi) & (slope >= slo) & (slope <= shi)
    lab, n = ndimage.label(m)
    if n == 0:
        continue
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    print('=== 高程 %d-%d m, 坡度 %d-%d deg : %d 块, 合计 %.0f km2 ===' % (
        elo, ehi, slo, shi, n, m.sum() * 900 / 1e6))
    for k in order[:6]:
        sel = (lab == k + 1)
        rr, cc = np.where(sel)
        pk = A[rr, cc].max()
        mn = A[rr, cc].mean()
        lon, lat = ll(int(rr.mean()), int(cc.mean()))
        # 最近主沟道距离
        d = min(np.hypot((rr - r0) * RES, (cc - c0) * RES).min()
                for r0, c0 in ch)
        area = sizes[k] * 900 / 1e6
        print('   块%3d  %5.1f km2  均高%5.0f 峰%5.0f m  中心 %.4fE %.4fN  距主沟 %5.2f km' % (
            k + 1, area, mn, pk, lon, lat, d / 1000))
    print()

# 沿主沟道找最陡的一段（可能的 1.2 km 下坠段）
print('=== 主沟道沿程陡度（找下坠段） ===')
for i in range(len(ch) - 1):
    r0, c0 = ch[i]; r1, c1 = ch[i + 1]
    dz = A[r0, c0] - A[r1, c1]
    dd = np.hypot((r1 - r0) * RES, (c1 - c0) * RES)
    if dd > 0:
        print('  row%4d->%4d  水平 %5.1f km  落差 %5.0f m  平均坡度 %4.1f%%  (%.1f deg)' % (
            r0, r1, dd / 1000, dz, 100 * dz / dd, np.degrees(np.arctan(dz / dd))))
