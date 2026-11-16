# -*- coding: utf-8 -*-
"""
为 Blender 导出两套数据:
  A) 高精度地形: 从原始 DEM 以原生 30 m 重采样 (533 x 407)
  B) 流体层: MassFlow mf_hi 结果的 H 场, 全部 121 帧 (10 s 间隔)
     —— 严格保持求解网格 20 m x 140 m, 不做去卷积式"假加密"

输出: F:\DeepSeek工作区\jilong\blender\flow_data.npz
"""
import os
import json
import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()
B = r'F:\DeepSeek工作区\jilong'
SRCDEM = r'D:\下载 (1)\2026年8月26日日喀则市吉隆县泥石流灾害区DEM数据\DEM.tif'
RUN = os.path.join(B, 'mf_hi')
OUTDIR = os.path.join(B, 'blender')
os.makedirs(OUTDIR, exist_ok=True)

# 域: 与 mf_hi 完全一致, 便于流体层对齐
meta = json.load(open(os.path.join(RUN, 'meta.json')))
E0, N0, N1 = meta['E0'], meta['N0'], meta['N1']
E1 = meta['E1']
fNX, fNY, fDX, fDY = meta['NX'], meta['NY'], meta['DX'], meta['DY']
print('流体网格: %d x %d = %s  (dx=%.0f, dy=%.0f)' % (fNX, fNY, format(fNX * fNY, ','), fDX, fDY))
print('域: E %.0f..%.0f  N %.0f..%.0f' % (E0, E1, N0, N1))

# ---------------- A) 高精度地形: 原生 30 m ----------------
TRES = 30.0
mem = gdal.Warp('', SRCDEM, dstSRS='EPSG:32645',
                outputBounds=[E0, N0, E1, N1], xRes=TRES, yRes=TRES,
                resampleAlg='bilinear', format='MEM',
                srcNodata=-32767, dstNodata=-9999)
ZT = mem.GetRasterBand(1).ReadAsArray().astype('f4')
tNY, tNX = ZT.shape
vt = ZT > -1000
if not vt.all():
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~vt, return_distances=False, return_indices=True)
    ZT[~vt] = ZT[tuple(idx[:, ~vt])]
print('地形: %d x %d = %s 顶点  (%.0f m 均匀)  Z %.0f..%.0f m'
      % (tNX, tNY, format(tNX * tNY, ','), TRES, ZT.min(), ZT.max()))

# ---------------- B) 流体层: 读全部帧 ----------------
import sys
sys.path.insert(0, B)
from plt_reader import iter_zones

frames, times = [], []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    frames.append(a[:, :, 4].astype(np.float32))     # H
    times.append(float(t))
H = np.stack(frames)                                  # (nf, fNY, fNX)
times = np.array(times, np.float32)
print('流体: %d 帧  t=%.0f..%.0f s  H 最大 %.1f m' % (len(times), times[0], times[-1], H.max()))

# 湿区范围 (用于裁剪流体网格, 只保留会被淹没的单元格)
wet_any = (H > 0.05).any(axis=0)
rr = np.where(wet_any.any(axis=1))[0]
cc = np.where(wet_any.any(axis=0))[0]
r0, r1 = max(0, rr.min() - 2), min(fNY, rr.max() + 3)
c0, c1 = max(0, cc.min() - 2), min(fNX, cc.max() + 3)
print('湿区范围 row %d..%d  col %d..%d  -> 裁为 %d x %d = %s'
      % (r0, r1, c0, c1, c1 - c0, r1 - r0, format((c1 - c0) * (r1 - r0), ',')))
Hc = H[:, r0:r1, c0:c1]

out = os.path.join(OUTDIR, 'flow_data.npz')
np.savez_compressed(
    out,
    # 地形
    terrain_Z=ZT, terrain_res=np.float32(TRES),
    tNX=np.int32(tNX), tNY=np.int32(tNY),
    # 流体
    H=Hc,
    fDX=np.float32(fDX), fDY=np.float32(fDY),
    f_col0=np.int32(c0), f_row0=np.int32(r0),
    fNX=np.int32(c1 - c0), fNY=np.int32(r1 - r0),
    times=times,
    # 域
    E0=np.float64(E0), N0=np.float64(N0), N1=np.float64(N1),
    # 锚点
    src_col=np.float32(meta['src_col'] - c0), src_row=np.float32(meta['src_row'] - r0),
    lake_col=np.float32(meta['lake_col'] - c0), lake_row=np.float32(meta['lake_row'] - r0),
    port_col=np.float32(meta['port_col'] - c0), port_row=np.float32(meta['port_row'] - r0),
    src_abs_col=np.float32(meta['src_col']), src_abs_row=np.float32(meta['src_row']),
    lake_abs_col=np.float32(meta['lake_col']), lake_abs_row=np.float32(meta['lake_row']),
    port_abs_col=np.float32(meta['port_col']), port_abs_row=np.float32(meta['port_row']),
)
sz = os.path.getsize(out) / 1e6
print()
print('已写出 %s  (%.1f MB)' % (out, sz))
print('  terrain_Z %s   H %s' % (ZT.shape, Hc.shape))
print('  压缩比: 原始 %.1f MB -> %.1f MB' % (
    (ZT.size + Hc.size) * 4 / 1e6, sz))
print('EXPORT_OK')
