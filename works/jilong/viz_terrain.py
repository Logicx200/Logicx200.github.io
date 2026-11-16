# -*- coding: utf-8 -*-
"""
地形+河网联合可视化，核实河谷走向与口岸位置。
输出 ASCII 晕渲（叠加河网标记）与统计，便于直接判读。
"""
import numpy as np
from osgeo import osr

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
acc = np.load(W + r'\flowacc.npy')
ny, nx = A.shape
E0, N1, RES = 322000, 3161000, 30

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s2, s1)


def ll(r, c):
    lon, lat, _ = ct.TransformPoint(float(E0 + c * RES), float(N1 - r * RES))
    return lon, lat


valid = A > -1000
Af = np.where(valid, A, np.nan)

# 河网分级
r200 = acc > 200
r1000 = acc > 1000
r5000 = acc > 5000

print('=== 河网统计 ===')
print('  累积>200  (约0.18 km2): %6d 像元' % r200.sum())
print('  累积>1000 (约0.9 km2) : %6d 像元' % r1000.sum())
print('  累积>5000 (约4.5 km2) : %6d 像元' % r5000.sum())
print('  最大累积 = %.0f 格 (%.0f km2)' % (acc.max(), acc.max() * 900 / 1e6))
i = np.unravel_index(np.argmax(acc), acc.shape)
print('  最大累积点 row=%d col=%d 高程=%.0f m  经纬度 %.4fE %.4fN' % (
    i[0], i[1], A[i], *ll(i[0], i[1])))

# 河网骨架按行列出
print()
print('=== 主干（累积>1000）逐行位置 ===')
rows = np.where(r1000.any(axis=1))[0]
if len(rows):
    for k in range(0, len(rows), max(1, len(rows) // 20)):
        r = rows[k]
        cs = np.where(r1000[r])[0]
        # 合并相邻列
        groups = []
        st = cs[0]; pv = cs[0]
        for c in cs[1:]:
            if c - pv > 3:
                groups.append((st, pv)); st = c
            pv = c
        groups.append((st, pv))
        gs = ' '.join('%d-%d(%.0fm)' % (a, b, A[r, (a + b) // 2]) for a, b in groups[:4])
        print('  row%4d lat%.3f  %s' % (r, ll(r, 0)[1], gs))

# ASCII 晕渲 + 河网
print()
CH = ' .:-=+*#%@'
ny2, nx2 = 60, 90
sy, sx = ny // ny2, nx // nx2
sub = np.nanmean(Af[:ny2 * sy, :nx2 * sx].reshape(ny2, sy, nx2, sx), axis=(1, 3))
gy, gx = np.gradient(np.nan_to_num(sub, nan=np.nanmean(sub)))
sh = (-gx * 0.8 - gy * 0.8)
sh = (sh - np.nanmin(sh)) / (np.nanmax(sh) - np.nanmin(sh) + 1e-9)
# 河网降采样标记
riv = np.zeros((ny2, nx2), bool)
riv5 = np.zeros((ny2, nx2), bool)
for r in range(ny2):
    for c in range(nx2):
        blk1 = r1000[r * sy:(r + 1) * sy, c * sx:(c + 1) * sx]
        blk5 = r5000[r * sy:(r + 1) * sy, c * sx:(c + 1) * sx]
        riv[r, c] = blk1.any()
        riv5[r, c] = blk5.any()
print('=== 地形晕渲 + 河网 ( / =累积>1000,  O =累积>5000 ) ===')
print('      ' + ''.join('|' if i % 10 == 0 else ' ' for i in range(nx2)))
for r in range(ny2):
    line = ''
    for c in range(nx2):
        if riv5[r, c]:
            line += 'O'
        elif riv[r, c]:
            line += '/'
        else:
            v = sub[r, c]
            line += '~' if not np.isfinite(v) else CH[min(9, max(0, int(sh[r, c] * 10)))]
    print('%5.2fN %s' % (ll(r * sy + sy // 2, 0)[1], line))
print('      经度: ' + ' '.join('%.2f' % ll(0, c * sx)[0] for c in range(0, nx2, 10)))
